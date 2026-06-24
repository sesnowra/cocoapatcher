"""Hardware report validation and manual GPU fixups for OpCore schema."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cocoapatcher import paths
from cocoapatcher.core.hardware_report import load_report_json

VALID_GPU_MANUFACTURERS = frozenset({"Intel", "AMD", "NVIDIA"})
VALID_GPU_DEVICE_TYPES = frozenset({"Integrated GPU", "Discrete GPU", "Unknown"})
_DEVICE_ID_RE = re.compile(r"^[0-9A-F]{4}(?:-[0-9A-F]{4})?$", re.IGNORECASE)

_JUNK_GPU_NAME_HINTS = (
    "microsoft",
    "basic display",
    "기본 디스플레이",
    "display adapter",
)


class ReportValidationError(ValueError):
    """OpCore report validation failed; GPU manual input may be required."""

    def __init__(self, errors: list[str], report_path: Path | None = None) -> None:
        self.errors = errors
        self.report_path = report_path
        super().__init__("Invalid hardware report: " + "; ".join(errors))


@dataclass
class GpuFixItem:
    name: str
    props: dict[str, Any]
    issues: list[str] = field(default_factory=list)
    suggest_remove: bool = False


def _is_junk_gpu_name(name: str) -> bool:
    lower = name.casefold()
    return any(hint in lower for hint in _JUNK_GPU_NAME_HINTS)


def inspect_gpu_entries(report: dict[str, Any]) -> list[GpuFixItem]:
    """Find GPU blocks that fail OpCore schema (need manual edit or removal)."""
    items: list[GpuFixItem] = []
    gpus = report.get("GPU") or {}
    if not isinstance(gpus, dict):
        return items

    for name, props in gpus.items():
        if not isinstance(props, dict):
            continue
        issues: list[str] = []
        mfr = props.get("Manufacturer")
        if mfr is None:
            issues.append("Missing Manufacturer (Intel, AMD, or NVIDIA)")
        elif mfr not in VALID_GPU_MANUFACTURERS:
            issues.append(f"Manufacturer '{mfr}' is invalid")

        dtype = props.get("Device Type")
        if dtype is None:
            issues.append("Missing Device Type")
        elif dtype not in VALID_GPU_DEVICE_TYPES:
            issues.append(f"Device Type '{dtype}' is invalid")

        if not props.get("Codename"):
            issues.append("Missing Codename")

        device_id = props.get("Device ID", "")
        if not device_id:
            issues.append("Missing Device ID")
        elif not _DEVICE_ID_RE.match(str(device_id)):
            issues.append(f"Device ID '{device_id}' has invalid format")

        if issues:
            suggest_remove = _is_junk_gpu_name(name) or str(mfr) == "Unknown"
            items.append(
                GpuFixItem(
                    name=name,
                    props=dict(props),
                    issues=issues,
                    suggest_remove=suggest_remove,
                )
            )
    return items


def gpu_errors_from_messages(errors: list[str]) -> list[str]:
    """GPU entry names mentioned in OpCore validation errors."""
    names: list[str] = []
    for err in errors:
        if ".GPU." not in err:
            continue
        try:
            segment = err.split(".GPU.", 1)[1]
            name = segment.split(".", 1)[0]
            if name and name not in names:
                names.append(name)
        except IndexError:
            continue
    return names


def _get_validator():
    paths.add_opcore_to_syspath()
    from Scripts.report_validator import ReportValidator

    return ReportValidator()


def validate_report_data(data: dict[str, Any]) -> tuple[bool, list[str], list[str], dict[str, Any] | None]:
    validator = _get_validator()
    validator.errors = []
    validator.warnings = []
    cleaned = validator._validate_node(data, validator.SCHEMA, "Root")
    is_valid = len(validator.errors) == 0
    return is_valid, validator.errors, validator.warnings, cleaned


def validate_report_dict(data: dict[str, Any]) -> tuple[bool, list[str], list[str], dict[str, Any] | None]:
    return validate_report_data(data)


def validate_report_file(path: Path) -> tuple[bool, list[str], list[str], dict[str, Any] | None]:
    return validate_report_data(load_report_json(path))


def save_report_json(path: Path, data: dict[str, Any]) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    return path


def apply_gpu_edit(
    report: dict[str, Any],
    gpu_name: str,
    *,
    remove: bool = False,
    manufacturer: str | None = None,
    codename: str | None = None,
    device_type: str | None = None,
) -> dict[str, Any]:
    report = json.loads(json.dumps(report))
    gpus = report.setdefault("GPU", {})
    if remove:
        gpus.pop(gpu_name, None)
        monitors = report.get("Monitor") or {}
        for mon_name, mon in list(monitors.items()):
            if isinstance(mon, dict) and mon.get("Connected GPU") == gpu_name:
                monitors.pop(mon_name, None)
        return report

    props = gpus.get(gpu_name)
    if not isinstance(props, dict):
        raise KeyError(f"GPU not found: {gpu_name}")

    if manufacturer is not None:
        if manufacturer not in VALID_GPU_MANUFACTURERS:
            raise ValueError(f"Manufacturer must be one of {sorted(VALID_GPU_MANUFACTURERS)}")
        props["Manufacturer"] = manufacturer
    if codename is not None:
        props["Codename"] = codename.strip()
    if device_type is not None:
        if device_type not in VALID_GPU_DEVICE_TYPES:
            raise ValueError(f"Device Type must be one of {sorted(VALID_GPU_DEVICE_TYPES)}")
        props["Device Type"] = device_type
    return report


def try_auto_remove_junk_gpus(report: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Remove obvious junk GPUs when at least one valid GPU remains."""
    items = inspect_gpu_entries(report)
    removable = [i.name for i in items if i.suggest_remove]
    if not removable:
        return report, []

    gpus = report.get("GPU") or {}
    remaining_valid = [
        name
        for name, props in gpus.items()
        if name not in removable and name not in {i.name for i in items}
    ]
    if not remaining_valid:
        return report, []

    removed: list[str] = []
    data = report
    for name in removable:
        data = apply_gpu_edit(data, name, remove=True)
        removed.append(name)
    return data, removed


def ensure_valid_report(
    report_path: Path,
    *,
    parent=None,
    log: Callable[[str], None] | None = None,
    prompt_manual: Callable[[Path, dict[str, Any], list[GpuFixItem]], dict[str, Any] | None]
    | None = None,
) -> Path | None:
    """
    Validate report; optionally prompt for manual GPU fixes.
    Returns path to a valid report file, or None if cancelled / still invalid.
    """
    report_path = report_path.resolve()
    data = load_report_json(report_path)
    ok, errors, warnings, _cleaned = validate_report_file(report_path)

    for warning in warnings:
        if log:
            log(f"Report warning: {warning}")

    if ok:
        return report_path

    gpu_items = inspect_gpu_entries(data)
    if not gpu_items and errors:
        if log:
            log("Invalid hardware report:")
            for err in errors:
                log(f"  {err}")
        raise ReportValidationError(errors, report_path)

    if prompt_manual is None:
        raise ReportValidationError(errors, report_path)

    if log:
        log("Hardware report needs manual GPU input (invalid or placeholder GPU entries).")

    fixed = prompt_manual(report_path, data, gpu_items)
    if fixed is None:
        if log:
            log("GPU fix cancelled.")
        return None

    ok, errors, warnings, _ = validate_report_dict(fixed)
    for warning in warnings:
        if log:
            log(f"Report warning: {warning}")
    if not ok:
        raise ReportValidationError(errors, report_path)

    save_report_json(report_path, fixed)
    if log:
        log(f"Saved fixed hardware report: {report_path}")
    return report_path
