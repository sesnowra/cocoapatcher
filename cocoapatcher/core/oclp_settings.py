"""OCLP Configurator settings (mirrors OpenCore Legacy Patcher GUI flags)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from cocoapatcher import paths

OCLP_NVRAM_GUID = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"


@dataclass
class OclpSettings:
    """Portable OCLP settings for cocoapatcher → embedded USB → macOS OCLP."""

    target_model: str = "MacPro7,1"

    # Build
    firewire_boot: bool = False
    xhci_boot: bool = False
    nvme_boot: bool = False
    vault: bool = False
    showpicker: bool = True
    oc_timeout: int = 5
    force_quad_thread: bool = False
    verbose_debug: bool = False
    kext_debug: bool = False
    opencore_debug: bool = False

    # Extras
    enable_wake_on_wlan: bool = False
    disable_tb: bool = False
    dGPU_switch: bool = False
    disallow_cpufriend: bool = False
    disable_mediaanalysisd: bool = False
    set_alc_usage: bool = True
    nvram_write: bool = True
    allow_nvme_fixing: bool = True
    allow_3rd_party_drives: bool = True
    apfs_trim_timeout: bool = True

    # Advanced
    disable_fw_throttle: bool = False
    software_demux: bool = False
    disable_connectdrivers: bool = False
    amd_gop_injection: bool = True
    nvidia_kepler_gop_injection: bool = False
    fu_status: bool = False
    fu_partial: bool = False

    # Security
    disable_cs_lv: bool = True
    disable_amfi: bool = True
    secure_status: bool = False
    sip_status: bool = False
    custom_sip_value: str | None = None

    # SMBIOS (OCLP EFI build / spoof)
    serial_settings: str = "None"
    override_smbios: str = "Default"
    allow_native_spoofs: bool = False

    # Root patching / mixed_tahoe
    allow_ts2_accel: bool = False
    force_surplus: bool = False
    force_latest_psp: bool = True

    # NVRAM OCLP-Settings boot-args (4D1FDA02-…)
    nvram_allow_amfi: bool = True
    nvram_allow_fv: bool = False
    extra_oclp_settings: str = ""

    notes: str = ""


SETTING_SECTIONS: dict[str, list[tuple[str, str, str]]] = {
    "Target": [
        ("target_model", "choice", "OCLP target Mac model for patch detection / EFI build"),
    ],
    "Build": [
        ("showpicker", "bool", "Show OpenCore boot picker"),
        ("oc_timeout", "int", "Boot picker timeout (seconds, 0 = none)"),
        ("nvram_write", "bool", "Allow OpenCore NVRAM write to flash"),
        ("verbose_debug", "bool", "Verbose boot (-v)"),
        ("kext_debug", "bool", "DEBUG kexts + kernel logging"),
        ("opencore_debug", "bool", "DEBUG OpenCore build"),
        ("firewire_boot", "bool", "FireWire boot support"),
        ("nvme_boot", "bool", "NVMe boot support (legacy platforms)"),
        ("xhci_boot", "bool", "USB 3.0 add-in card boot"),
        ("vault", "bool", "OpenCore vault signing"),
        ("force_quad_thread", "bool", "MacPro3,1 / Xserve2,1 quad-thread workaround"),
    ],
    "Extras": [
        ("enable_wake_on_wlan", "bool", "Wake on WLAN (Broadcom)"),
        ("disable_tb", "bool", "Disable Thunderbolt (MacBookPro11,x)"),
        ("dGPU_switch", "bool", "Windows GMUX / iGPU expose"),
        ("disallow_cpufriend", "bool", "Disable CPUFriend"),
        ("set_alc_usage", "bool", "Allow AppleALC"),
        ("allow_nvme_fixing", "bool", "3rd-party NVMe power management"),
        ("allow_3rd_party_drives", "bool", "3rd-party SATA power management"),
        ("apfs_trim_timeout", "bool", "APFS trim timeout quirk"),
        ("disable_mediaanalysisd", "bool", "Disable mediaanalysisd (3802 iCloud hosts)"),
    ],
    "Advanced": [
        ("disable_fw_throttle", "bool", "Disable firmware throttling"),
        ("software_demux", "bool", "Software DeMUX (MacBookPro8,2/8,3)"),
        ("disable_connectdrivers", "bool", "Hibernation workaround (minimal drivers)"),
        ("amd_gop_injection", "bool", "AMD GOP injection (PC dGPU boot screen)"),
        ("nvidia_kepler_gop_injection", "bool", "Nvidia Kepler GOP injection"),
        ("fu_status", "bool", "FeatureUnlock enabled"),
        ("fu_partial", "bool", "FeatureUnlock partial (-disable_sidecar_mac)"),
    ],
    "Security": [
        ("disable_cs_lv", "bool", "Disable library validation (root patch)"),
        ("disable_amfi", "bool", "Disable AMFI (deep root patches)"),
        ("sip_status", "bool", "SIP fully enabled (csr-active-config)"),
        ("secure_status", "bool", "Secure Boot Model (T2 spoof)"),
    ],
    "SMBIOS (OCLP)": [
        ("serial_settings", "choice_smbios_level", "Spoof level: None / Minimal / Moderate / Advanced"),
        ("override_smbios", "str", "Override SMBIOS model (Default = auto)"),
        ("allow_native_spoofs", "bool", "Spoof on natively supported Macs"),
    ],
    "Root Patching": [
        ("allow_ts2_accel", "bool", "TeraScale 2 acceleration (MacBookPro8,2/8,3)"),
        ("force_surplus", "bool", "Force SurPlus patch"),
        ("force_latest_psp", "bool", "Prefer latest PatcherSupportPkg payloads"),
    ],
    "NVRAM OCLP-Settings": [
        ("nvram_allow_amfi", "bool", "Append -allow_amfi to OCLP-Settings"),
        ("nvram_allow_fv", "bool", "Append -allow_fv to OCLP-Settings"),
        ("extra_oclp_settings", "str", "Extra OCLP-Settings tokens (space-separated)"),
    ],
}

SMBIOS_LEVELS = ["None", "Minimal", "Moderate", "Advanced"]


def settings_path() -> Path:
    env = __import__("os").environ.get("COCOAPATCHER_OCLP_SETTINGS")
    if env:
        return Path(env).expanduser().resolve()
    return paths.sniffer_cache_dir() / "oclp-settings.json"


def load_settings(path: Path | None = None) -> OclpSettings:
    p = path or settings_path()
    if not p.is_file():
        return OclpSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        known = {f.name for f in OclpSettings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return OclpSettings(**filtered)
    except (json.JSONDecodeError, TypeError, ValueError):
        return OclpSettings()


def save_settings(settings: OclpSettings, path: Path | None = None) -> Path:
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    return p


def list_oclp_target_models() -> list[str]:
    paths.add_oclp_to_syspath()
    from opencore_legacy_patcher.datasets import model_array

    return list(model_array.SupportedSMBIOS)


def build_oclp_settings_nvram(settings: OclpSettings) -> str:
    tokens: list[str] = []
    if settings.nvram_allow_amfi:
        tokens.append("-allow_amfi")
    if settings.nvram_allow_fv:
        tokens.append("-allow_fv")
    if settings.extra_oclp_settings.strip():
        tokens.extend(settings.extra_oclp_settings.strip().split())
    return " ".join(tokens).strip()


def to_gui_plist_entries(settings: OclpSettings) -> dict[str, Any]:
    """Map to OCLP GlobalEnviromentSettings GUI: keys (macOS plist on target)."""
    data = asdict(settings)
    out: dict[str, Any] = {}
    skip = {
        "notes",
        "nvram_allow_amfi",
        "nvram_allow_fv",
        "extra_oclp_settings",
        "fu_partial",
        "target_model",
    }
    for key, value in data.items():
        if key in skip:
            continue
        if key == "fu_partial":
            continue
        if value is None:
            out[f"GUI:{key}"] = "PYTHON_NONE_VALUE"
        else:
            out[f"GUI:{key}"] = value

    if settings.fu_partial:
        out["GUI:fu_status"] = True
        out["GUI:fu_arguments"] = " -disable_sidecar_mac"
    elif settings.fu_status:
        out["GUI:fu_status"] = True
        out["GUI:fu_arguments"] = "PYTHON_NONE_VALUE"
    else:
        out["GUI:fu_status"] = False
        out["GUI:fu_arguments"] = "PYTHON_NONE_VALUE"

    out["GUI:custom_model"] = settings.target_model
    return out


def format_settings_report(settings: OclpSettings | None = None) -> str:
    s = settings or load_settings()
    lines = [
        f"target_model={s.target_model}",
        f"OCLP-Settings ({OCLP_NVRAM_GUID}): {build_oclp_settings_nvram(s) or '(empty)'}",
        f"disable_cs_lv={s.disable_cs_lv} disable_amfi={s.disable_amfi} sip_status={s.sip_status}",
        f"amd_gop_injection={s.amd_gop_injection} force_latest_psp={s.force_latest_psp}",
        "",
        "Environment (embed / runtime):",
    ]
    try:
        oclp = paths.oclp_root()
        lines.append(f"  OCLP_PATH={oclp}")
        lines.append(f"  patcher_version={_oclp_constants().patcher_version}")
        lines.append(f"  PSP={_oclp_constants().patcher_support_pkg_version}")
    except Exception as exc:
        lines.append(f"  (OCLP paths unavailable: {exc})")
    import os

    if os.environ.get("OCLP_PSP_LOCAL"):
        lines.append(f"  OCLP_PSP_LOCAL={os.environ['OCLP_PSP_LOCAL']}")
    if os.environ.get("OCLP_PSP_URL"):
        lines.append(f"  OCLP_PSP_URL={os.environ['OCLP_PSP_URL']}")
    lines.append("")
    for section, items in SETTING_SECTIONS.items():
        lines.append(f"[{section}]")
        for key, _kind, label in items:
            if not hasattr(s, key):
                continue
            val = getattr(s, key)
            lines.append(f"  {key}={val}  # {label}")
        lines.append("")
    return "\n".join(lines).rstrip()


def iter_enabled_flags(settings: OclpSettings) -> Iterator[str]:
    for section, items in SETTING_SECTIONS.items():
        for key, kind, label in items:
            if kind != "bool":
                continue
            if getattr(settings, key, False):
                yield f"{section}: {key}"


def _oclp_constants():
    paths.add_oclp_to_syspath()
    from opencore_legacy_patcher import constants

    return constants.Constants()


def export_gui_plist(settings: OclpSettings, path: Path) -> Path:
    import plistlib

    path.parent.mkdir(parents=True, exist_ok=True)
    plistlib.dump(to_gui_plist_entries(settings), path.open("wb"))
    return path


def tahoe_gcn_preset() -> OclpSettings:
    """Suggested defaults for AMD Legacy GCN + Tahoe root patching."""
    return OclpSettings(
        target_model="MacPro7,1",
        disable_cs_lv=True,
        disable_amfi=True,
        sip_status=False,
        amd_gop_injection=True,
        nvram_allow_amfi=True,
        force_latest_psp=True,
        verbose_debug=False,
    )
