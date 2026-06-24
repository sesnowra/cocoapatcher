"""SMBIOS model selection (OpCore-Simplify mac_devices + OCLP + heuristics)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from cocoapatcher import paths
from cocoapatcher.core.macos_versions import to_darwin_version


class SmbiosProfile(str, Enum):
    """How PlatformInfo / model selection is presented to the user."""

    MACINTOSH = "macintosh"  # EFI Build — pick a Mac model identifier
    CUSTOM = "custom"  # Hardware Sniffer — auto from hardware, editable


@dataclass(frozen=True)
class SmbiosChoice:
    model: str
    profile: SmbiosProfile
    auto_suggested: bool = False


# Common OCLP / spoof targets not listed in OpCore mac_devices.
SUPPLEMENTAL_SMBIOS: tuple[str, ...] = (
    "MacBookAir10,1",
    "MacBookPro17,1",
    "MacBookPro18,1",
    "MacBookPro18,2",
    "MacBookPro18,3",
    "MacBookPro18,4",
    "Mac13,1",
    "Mac13,2",
    "Mac14,7",
    "Macmini9,1",
    "Macmini10,1",
    "Macmini10,2",
    "iMac21,1",
    "iMac21,2",
    "iMac22,1",
    "iMac22,2",
    "MacPro6,1",
    "MacPro7,1",
    "iMacPro1,1",
    "MacBookPro15,1",
    "MacBookPro16,1",
    "MacBookPro16,4",
    "iMac19,1",
    "iMac20,1",
    "iMac20,2",
)


def _opcore_mac_device_names() -> list[str]:
    root = paths.opcore_root()
    if not (root / "Scripts" / "datasets" / "mac_model_data.py").is_file():
        from cocoapatcher.core.opcore_static import parse_mac_devices_from_disk

        return parse_mac_devices_from_disk()
    try:
        paths.add_opcore_to_syspath()
        from Scripts.datasets.mac_model_data import mac_devices

        return [device.name for device in mac_devices]
    except (ImportError, ModuleNotFoundError):
        from cocoapatcher.core.opcore_static import parse_mac_devices_from_disk

        return parse_mac_devices_from_disk()


def _opcore_smbios():
    root = paths.opcore_root()
    if not (root / "Scripts" / "smbios.py").is_file():
        raise RuntimeError(f"OpCore-Simplify not found at {root}")
    paths.add_opcore_to_syspath()
    from Scripts.smbios import SMBIOS

    return SMBIOS()


def _oclp_smbios_names() -> list[str]:
    smbios_py = (
        paths.oclp_root()
        / "opencore_legacy_patcher"
        / "datasets"
        / "smbios_data.py"
    )
    if not smbios_py.is_file():
        return []
    text = smbios_py.read_text(encoding="utf-8", errors="replace")
    names = re.findall(r'"((?:Mac|iMac)[^"]+)"\s*:\s*\{', text)
    cleaned: list[str] = []
    for name in names:
        base = name.split("_")[0]
        if base not in cleaned:
            cleaned.append(base)
    return cleaned


def all_known_smbios_models() -> list[str]:
    """Union of OpCore, OCLP, and supplemental identifiers (sorted, deduped)."""
    seen: set[str] = set()
    ordered: list[str] = []
    pool = _opcore_mac_device_names() + _oclp_smbios_names() + list(SUPPLEMENTAL_SMBIOS)
    if not pool or pool == list(SUPPLEMENTAL_SMBIOS):
        from cocoapatcher.core.opcore_static import fallback_smbios_models

        pool = fallback_smbios_models()
    for name in pool:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return sorted(ordered, key=_smbios_sort_key) if ordered else sorted(SUPPLEMENTAL_SMBIOS, key=_smbios_sort_key)


def _smbios_sort_key(name: str) -> tuple[str, int, int]:
    prefix = ""
    major = minor = 0
    for char in name:
        if char.isdigit():
            break
        prefix += char
    match = re.search(r"(\d+),(\d+)", name)
    if match:
        major, minor = int(match.group(1)), int(match.group(2))
    return (prefix, major, minor)


def suggest_model(hardware_report: dict[str, Any], macos_version: str) -> str:
    return _opcore_smbios().select_smbios_model(hardware_report, macos_version)


def list_models(
    hardware_report: dict[str, Any],
    macos_version: str,
    *,
    compatible_only: bool = True,
    form_factor_match: bool = False,
) -> list[str]:
    root = paths.opcore_root()
    if not (root / "Scripts" / "datasets" / "mac_model_data.py").is_file():
        default = "MacPro7,1"
        try:
            default = suggest_model(hardware_report, macos_version)
        except Exception:
            pass
        pool = all_known_smbios_models() if not compatible_only else [default, *SUPPLEMENTAL_SMBIOS]
        return list(dict.fromkeys(pool))

    paths.add_opcore_to_syspath()
    try:
        from Scripts.datasets.mac_model_data import mac_devices
        from Scripts import utils
    except (ImportError, ModuleNotFoundError):
        return all_known_smbios_models()

    u = utils.Utils()
    darwin_version = to_darwin_version(macos_version)
    platform = hardware_report.get("Motherboard", {}).get("Platform", "Desktop")
    is_laptop = platform == "Laptop"
    default = suggest_model(hardware_report, macos_version)
    models: list[str] = []

    def _add(name: str) -> None:
        if name not in models:
            models.append(name)

    _add(default)
    for device in mac_devices:
        supported = (
            u.parse_darwin_version(device.initial_support)
            <= u.parse_darwin_version(darwin_version)
            <= u.parse_darwin_version(device.last_supported_version)
        )
        if compatible_only and not supported:
            continue
        if form_factor_match and is_laptop and not device.name.startswith("MacBook"):
            continue
        if form_factor_match and not is_laptop and device.name.startswith("MacBook"):
            continue
        _add(device.name)

    pool = all_known_smbios_models() if not compatible_only else None
    if pool is not None:
        for name in pool:
            _add(name)
    else:
        for name in SUPPLEMENTAL_SMBIOS:
            if form_factor_match and is_laptop and not name.startswith("MacBook"):
                continue
            if form_factor_match and not is_laptop and name.startswith("MacBook"):
                continue
            _add(name)

    return models


def resolve_smbios(
    hardware_report: dict[str, Any],
    macos_version: str,
    profile: SmbiosProfile,
    selected: str | None,
) -> SmbiosChoice:
    suggested = suggest_model(hardware_report, macos_version)
    if profile == SmbiosProfile.CUSTOM:
        model = (selected or suggested).strip() or suggested
        return SmbiosChoice(model=model, profile=profile, auto_suggested=not selected)

    if not selected or not selected.strip():
        raise ValueError("Macintosh SMBIOS model is required for EFI Build.")
    model = selected.strip()
    known = set(all_known_smbios_models())
    if model not in known:
        raise ValueError(f"Unknown SMBIOS model: {model}")
    return SmbiosChoice(model=model, profile=profile, auto_suggested=False)
