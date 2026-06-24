"""OpCore OCPE headless wrapper for EFI builds."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from cocoapatcher import paths
from cocoapatcher.core.hardware_report import load_report_json
from cocoapatcher.core.smbios_picker import SmbiosProfile, list_models, resolve_smbios, suggest_model
from cocoapatcher.core.efi_marketplace import (
    MarketplaceEntry,
    MarketplaceRefOptions,
    apply_marketplace_overlay,
)
from cocoapatcher.core.device_compatibility import (
    DeviceCompatibility,
    DeviceCompatibilityError,
    analyze_hardware_report,
    compatible_macos_choices,
    needs_oclp_for_version,
    oclp_required_readonly,
)

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str, int, int], None]


@dataclass
class EfiBuildResult:
    output_dir: Path
    needs_oclp: bool
    smbios_model: str
    macos_version: str
    smbios_profile: SmbiosProfile = SmbiosProfile.MACINTOSH


def _load_ocpe_class():
    opcore = paths.opcore_root()
    if not opcore.is_dir():
        raise FileNotFoundError(f"OpCore-Simplify not found: {opcore}")
    if str(opcore) not in sys.path:
        sys.path.insert(0, str(opcore))
    oclp = paths.oclp_root()
    os.environ.setdefault("OCLP_PATH", str(oclp))
    os.environ.setdefault("OPENCORE_LEGACY_PATCHER_PATH", str(oclp))
    entry = opcore / "OpCore-Simplify.py"
    spec = importlib.util.spec_from_file_location("opcore_simplify", entry)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load OpCore from {entry}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OCPE


@contextlib.contextmanager
def _headless_opcore(ocpe, log: LogCallback):
    """Silence OpCore prompts; empty input selects documented defaults."""
    utils = ocpe.u
    original_request = utils.request_input
    original_head = utils.head
    original_progress = utils.progress_bar

    def _request_input(prompt=""):
        text = str(prompt).lower()
        if "uefi?" in text or "build efi for uefi" in text:
            return "yes"
        if "default:" in text:
            # e.g. kext selection prompts use "" for recommended option
            return ""
        return ""

    def _head(*_args, **_kwargs):
        return None

    def _progress_bar(title, steps, index, done=False):
        total = len(steps) if isinstance(steps, list) else int(steps or 1)
        log(f"{title} [{index}/{total}]")
        return original_progress(title, steps, index, done=done)

    utils.request_input = _request_input
    utils.head = _head
    utils.progress_bar = _progress_bar
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        utils.request_input = original_request
        utils.head = original_head
        utils.progress_bar = original_progress


class EfiBuilder:
    """Wrap OpCore-Simplify OCPE for non-interactive EFI generation."""

    def __init__(
        self,
        log: Optional[LogCallback] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> None:
        self._log = log or print
        self._progress = progress or (lambda _t, _s, _tot: None)
        self._ocpe = None

    def _ensure_ocpe(self):
        if self._ocpe is None:
            paths.ensure_vendor_paths()
            self._ocpe = _load_ocpe_class()()
        return self._ocpe

    def load_report(self, report_path: Path) -> dict[str, Any]:
        report_path = report_path.resolve()
        ocpe = self._ensure_ocpe()
        ok, errors, warnings, data = ocpe.v.validate_report(str(report_path))
        if not ok or data is None:
            raise ValueError("Invalid hardware report: " + "; ".join(errors))
        for warning in warnings:
            self._log(f"Report warning: {warning}")
        return data

    def load_report_dict(self, report_path: Path) -> dict[str, Any]:
        return load_report_json(report_path)

    def analyze_device(self, report_path: Path) -> DeviceCompatibility:
        return analyze_hardware_report(load_report_json(report_path))

    def compatible_macos_for_report(self, report_path: Path) -> list:
        return compatible_macos_choices(self.analyze_device(report_path))

    def compatible_macos_for_smbios(self, smbios_model: str) -> list:
        return compatible_macos_choices(smbios_model=smbios_model)

    def needs_oclp(self, report_path: Path, macos_version: str) -> bool:
        profile = self.analyze_device(report_path)
        return needs_oclp_for_version(profile, macos_version)

    def suggest_smbios(self, report_path: Path, macos_version: str) -> str:
        return suggest_model(load_report_json(report_path), macos_version)

    def list_smbios_models(
        self,
        report_path: Path,
        macos_version: str,
        *,
        compatible_only: bool = True,
        form_factor_match: bool = False,
    ) -> list[str]:
        return list_models(
            load_report_json(report_path),
            macos_version,
            compatible_only=compatible_only,
            form_factor_match=form_factor_match,
        )

    def build(
        self,
        report_path: Path,
        macos_version: str,
        output_dir: Optional[Path] = None,
        smbios_model: Optional[str] = None,
        smbios_profile: SmbiosProfile = SmbiosProfile.MACINTOSH,
        marketplace_entry: Optional[MarketplaceEntry] = None,
        marketplace_options: Optional[MarketplaceRefOptions] = None,
    ) -> EfiBuildResult:
        ocpe = self._ensure_ocpe()
        hardware_report = self.load_report(report_path)
        self._log(f"Loaded hardware report: {report_path}")

        with _headless_opcore(ocpe, self._log):
            hardware_report, native_macos_version, ocl_patched = ocpe.c.check_compatibility(
                hardware_report
            )
            customized, disabled_devices, needs_oclp = ocpe.h.hardware_customization(
                hardware_report, macos_version
            )
            choice = resolve_smbios(
                customized,
                macos_version,
                smbios_profile,
                smbios_model,
            )
            smbios_model = choice.model
            if choice.auto_suggested:
                self._log(f"Custom SMBIOS (auto): {smbios_model}")
            else:
                self._log(f"SMBIOS ({choice.profile.value}): {smbios_model}")
            if not ocpe.ac.ensure_dsdt():
                ocpe.ac.select_acpi_tables()
            ocpe.ac.select_acpi_patches(customized, disabled_devices)
            needs_oclp = ocpe.k.select_required_kexts(
                customized, macos_version, needs_oclp, ocpe.ac.patches
            )
            ocpe.s.smbios_specific_options(
                customized, smbios_model, macos_version, ocpe.ac.patches, ocpe.k
            )

        if output_dir:
            ocpe.result_dir = str(output_dir.resolve())
        else:
            output_dir = Path(ocpe.result_dir)

        self._log(
            f"Building EFI for macOS {macos_version}, SMBIOS {smbios_model}, "
            f"needs_oclp={needs_oclp}"
        )

        original_progress = ocpe.u.progress_bar

        def _progress_bar(title, steps, index, done=False):
            total = len(steps) if isinstance(steps, list) else int(steps or 1)
            self._progress(str(title), int(index), total)
            if done:
                self._log(f"{title}: complete")
            return original_progress(title, steps, index, done=done)

        ocpe.u.progress_bar = _progress_bar

        with _headless_opcore(ocpe, self._log):
            with contextlib.redirect_stdout(io.StringIO()):
                ocpe.o.gather_bootloader_kexts(ocpe.k.kexts, macos_version)
                ocpe.build_opencore_efi(
                    customized,
                    disabled_devices,
                    smbios_model,
                    macos_version,
                    needs_oclp,
                )

        result_dir = Path(ocpe.result_dir).resolve()
        if marketplace_entry and marketplace_options and marketplace_options.enabled:
            self._log(f"Applying EFI Marketplace: {marketplace_entry.id}")
            apply_marketplace_overlay(
                result_dir,
                marketplace_entry,
                macos_version,
                marketplace_options,
                log=self._log,
            )

        return EfiBuildResult(
            output_dir=result_dir,
            needs_oclp=needs_oclp,
            smbios_model=smbios_model,
            macos_version=macos_version,
            smbios_profile=choice.profile,
        )
