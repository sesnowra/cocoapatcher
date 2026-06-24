"""Static fallbacks when OpCore-Simplify cannot be imported (e.g. united.exe GUI startup)."""

from __future__ import annotations

import re
from pathlib import Path

from cocoapatcher import paths

# Mirrors OpCore-Simplify Scripts/datasets/os_data.py macos_versions
MACOS_VERSIONS: tuple[tuple[str, str, int], ...] = (
    ("High Sierra", "10.13", 17),
    ("Mojave", "10.14", 18),
    ("Catalina", "10.15", 19),
    ("Big Sur", "11", 20),
    ("Monterey", "12", 21),
    ("Ventura", "13", 22),
    ("Sonoma", "14", 23),
    ("Sequoia", "15", 24),
    ("Tahoe", "26", 25),
)


def parse_mac_devices_from_disk() -> list[str]:
    mac_model = paths.opcore_root() / "Scripts" / "datasets" / "mac_model_data.py"
    if not mac_model.is_file():
        return []
    text = mac_model.read_text(encoding="utf-8", errors="replace")
    return re.findall(r'MacDevice\("([^"]+)"', text)


def fallback_smbios_models() -> list[str]:
    names = parse_mac_devices_from_disk()
    supplemental = (
        "MacBookAir10,1",
        "MacBookPro17,1",
        "MacPro7,1",
        "iMacPro1,1",
        "iMac20,2",
    )
    if not names:
        names = list(supplemental)
    oclp_py = (
        paths.oclp_root()
        / "opencore_legacy_patcher"
        / "datasets"
        / "smbios_data.py"
    )
    if oclp_py.is_file():
        text = oclp_py.read_text(encoding="utf-8", errors="replace")
        for m in re.findall(r'"((?:Mac|iMac)[^"]+)"\s*:\s*\{', text):
            base = m.split("_")[0]
            if base not in names:
                names.append(base)
    for m in supplemental:
        if m not in names:
            names.append(m)
    return names
