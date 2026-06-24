"""Hardware-report macOS compatibility (OpCore CompatibilityChecker, headless)."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from typing import Any

from cocoapatcher import paths
from cocoapatcher.core.macos_versions import (
    MacosVersionChoice,
    list_macos_version_choices,
    to_darwin_version,
)


class DeviceCompatibilityError(RuntimeError):
    pass


@dataclass
class DeviceCompatibility:
    """macOS ranges for a hardware report after OpCore compatibility pass."""

    hardware_report: dict[str, Any]
    native_min: str
    native_max: str
    oclp_range: tuple[str, str] | None = None
    suggested_version: str = ""
    warnings: list[str] = field(default_factory=list)


def _parse_major(darwin_version: str) -> int:
    paths.add_opcore_to_syspath()
    from Scripts import utils

    return utils.Utils().parse_darwin_version(darwin_version)[0]


def _in_range(target: str, low: str, high: str) -> bool:
    paths.add_opcore_to_syspath()
    from Scripts import utils

    u = utils.Utils()
    t = u.parse_darwin_version(target)
    return u.parse_darwin_version(low) <= t <= u.parse_darwin_version(high)


def _suggest_darwin_version(hardware_report: dict[str, Any], native_max: str) -> str:
    paths.add_opcore_to_syspath()
    from Scripts.datasets import os_data
    from Scripts import utils

    u = utils.Utils()
    suggested = native_max
    for device_type in ("GPU", "Network", "Bluetooth", "SD Controller"):
        block = hardware_report.get(device_type)
        if not isinstance(block, dict):
            continue
        for device_props in block.values():
            compat = device_props.get("Compatibility", (None, None))
            if compat == (None, None):
                continue
            if device_type == "GPU" and device_props.get("Device Type") == "Integrated GPU":
                device_id = device_props.get("Device ID", "00000000")[5:]
                manufacturer = device_props.get("Manufacturer", "")
                if manufacturer == "AMD" or device_id.startswith(("59", "87C0")):
                    suggested = "22.99.99"
                elif device_id.startswith(("09", "19")):
                    suggested = "21.99.99"
            if compat[0] and u.parse_darwin_version(suggested) > u.parse_darwin_version(compat[0]):
                suggested = compat[0]

    while True:
        name = os_data.get_macos_name_by_darwin(suggested)
        if name and "Beta" in name:
            suggested = f"{int(suggested[:2]) - 1}{suggested[2:]}"
        else:
            break
    return suggested


def _run_compatibility_checker(hardware_report: dict[str, Any]) -> tuple[dict, tuple[str, str], tuple[str, str] | None]:
    paths.add_opcore_to_syspath()
    from Scripts.compatibility_checker import CompatibilityChecker
    from Scripts import utils

    checker = CompatibilityChecker()
    original_exit = utils.Utils.exit_program
    original_input = utils.Utils.request_input
    original_head = utils.Utils.head

    def _raise_exit(*_a, **_k):
        raise DeviceCompatibilityError("Hardware is not compatible with any supported macOS version.")

    utils.Utils.exit_program = _raise_exit
    utils.Utils.request_input = lambda *_a, **_k: ""
    utils.Utils.head = lambda *_a, **_k: None

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return checker.check_compatibility(hardware_report.copy())
    finally:
        utils.Utils.exit_program = original_exit
        utils.Utils.request_input = original_input
        utils.Utils.head = original_head


def analyze_hardware_report(hardware_report: dict[str, Any]) -> DeviceCompatibility:
    report, native, oclp = _run_compatibility_checker(hardware_report)
    native_min, native_max = native
    suggested = _suggest_darwin_version(report, native_max)
    return DeviceCompatibility(
        hardware_report=report,
        native_min=native_min,
        native_max=native_max,
        oclp_range=oclp,
        suggested_version=_darwin_to_marketing_choice(suggested).version,
    )


def _darwin_to_marketing_choice(darwin_version: str) -> MacosVersionChoice:
    major = _parse_major(darwin_version)
    for choice in list_macos_version_choices():
        if choice.darwin_major == major:
            return choice
    choices = list_macos_version_choices()
    return choices[-1]


def compatible_macos_choices(
    profile: DeviceCompatibility | None = None,
    *,
    smbios_model: str | None = None,
) -> list[MacosVersionChoice]:
    """Device- or SMBIOS-filtered macOS targets (10.13 … 26)."""
    all_choices = list_macos_version_choices()
    if profile is not None:
        min_major = _parse_major(profile.native_min)
        max_major = _parse_major(profile.native_max)
        oclp_min = oclp_max = None
        if profile.oclp_range:
            oclp_max = _parse_major(profile.oclp_range[0])
            oclp_min = _parse_major(profile.oclp_range[1])
        result: list[MacosVersionChoice] = []
        for choice in all_choices:
            d = choice.darwin_major
            native_ok = min_major <= d <= max_major
            oclp_ok = oclp_min is not None and oclp_max is not None and oclp_min <= d <= oclp_max
            if native_ok or oclp_ok:
                suffix = " — Requires OCLP" if oclp_ok and not native_ok else ""
                result.append(
                    MacosVersionChoice(
                        label=f"{choice.label}{suffix}",
                        version=choice.version,
                        darwin_major=choice.darwin_major,
                    )
                )
        return result

    if smbios_model:
        paths.add_opcore_to_syspath()
        from Scripts.datasets.mac_model_data import get_mac_device_by_name
        from Scripts import utils

        device = get_mac_device_by_name(smbios_model)
        if device is None:
            return all_choices
        u = utils.Utils()
        min_major = u.parse_darwin_version(device.initial_support)[0]
        max_major = u.parse_darwin_version(device.last_supported_version)[0]
        return [c for c in all_choices if min_major <= c.darwin_major <= max_major]

    return all_choices


def needs_oclp_for_version(
    profile: DeviceCompatibility,
    macos_version: str,
) -> bool:
    """True when target macOS is only supported via OCLP patching."""
    darwin = to_darwin_version(macos_version)
    in_native = _in_range(darwin, profile.native_min, profile.native_max)
    if in_native:
        return False
    if not profile.oclp_range:
        return False
    oclp_max, oclp_min = profile.oclp_range
    if not _in_range(darwin, oclp_min, oclp_max):
        return False
    for device_type in ("GPU", "Network", "Bluetooth", "SD Controller"):
        block = profile.hardware_report.get(device_type)
        if not isinstance(block, dict):
            continue
        for props in block.values():
            oclp = props.get("OCLP Compatibility")
            if oclp and _in_range(darwin, oclp[1], oclp[0]):
                return True
    return True


def oclp_required_readonly(profile: DeviceCompatibility, macos_version: str) -> bool:
    """OCLP checkbox should be forced on and read-only."""
    return needs_oclp_for_version(profile, macos_version)
