"""Apply OCLP Configurator settings from device + target macOS support tier."""

from __future__ import annotations

from dataclasses import replace

from cocoapatcher.core.device_compatibility import (
    DeviceCompatibility,
    VersionSupport,
    classify_version,
)
from cocoapatcher.core.oclp_settings import OclpSettings, load_settings, save_settings, tahoe_gcn_preset


def _gpu_hints(report: dict) -> tuple[bool, bool]:
    amd_gop = False
    nvidia_kepler = False
    for _name, props in (report.get("GPU") or {}).items():
        if props.get("Device Type") == "Integrated GPU":
            continue
        mfr = str(props.get("Manufacturer", ""))
        code = str(props.get("Codename", ""))
        if "AMD" in mfr:
            amd_gop = True
        if "NVIDIA" in mfr and ("Kepler" in code or "Maxwell" in code):
            nvidia_kepler = True
    return amd_gop, nvidia_kepler


def build_oclp_settings_for_target(
    profile: DeviceCompatibility,
    macos_version: str,
    smbios_model: str | None = None,
    *,
    force: bool = False,
) -> OclpSettings | None:
    """Return OCLP settings when unofficial tier is active or build requires root patches."""
    tier = classify_version(profile, macos_version)
    if tier != VersionSupport.OCLP_UNOFFICIAL and not force:
        return None

    preset = tahoe_gcn_preset()
    amd_gop, nvidia_kepler = _gpu_hints(profile.hardware_report)
    return replace(
        load_settings(),
        target_model=smbios_model or preset.target_model,
        disable_cs_lv=True,
        disable_amfi=True,
        sip_status=False,
        nvram_allow_amfi=True,
        force_latest_psp=True,
        amd_gop_injection=amd_gop or preset.amd_gop_injection,
        nvidia_kepler_gop_injection=nvidia_kepler,
        notes=(
            f"Auto: unofficial macOS {macos_version} via OCLP "
            f"(native darwin {profile.native_min}…{profile.native_max})"
        ),
    )


def apply_oclp_for_target(
    profile: DeviceCompatibility,
    macos_version: str,
    smbios_model: str | None = None,
    *,
    force: bool = False,
    log=None,
) -> OclpSettings | None:
    settings = build_oclp_settings_for_target(
        profile, macos_version, smbios_model, force=force
    )
    if settings is None:
        return None
    path = save_settings(settings)
    if log:
        log(f"OCLP settings saved for unofficial target ({path.name})")
        log(f"  target_model={settings.target_model} amd_gop={settings.amd_gop_injection}")
    return settings
