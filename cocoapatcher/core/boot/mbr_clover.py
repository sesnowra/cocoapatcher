"""MBR legacy boot via Clover chainloading OpenCore."""

from __future__ import annotations

import plistlib
import shutil
from pathlib import Path
from typing import Callable, Optional

from cocoapatcher import paths
from cocoapatcher.core.boot import gpt_opencore

LogFn = Callable[[str], None]


def _clover_config() -> dict:
    return {
        "ACPI": {"Add": [], "Delete": [], "Patch": []},
        "Boot": {
            "Timeout": 5,
            "DefaultBoot": "OpenCore",
        },
        "GUI": {"Hide": False, "Language": "en"},
        "RtVariables": {"BooterConfig": "0x28", "CsrActiveConfig": "0x67"},
        "SystemParameters": {"InjectKexts": "Detect"},
        "KernelAndKextPatches": {"KernelCpu": False},
        "SMBIOS": {"ProductName": "iMac18,3"},
        "CustomEntries": [
            {
                "Disabled": False,
                "Hide": False,
                "Image": "",
                "Path": "\\EFI\\OC\\OpenCore.efi",
                "Title": "OpenCore",
                "Type": "Other",
            }
        ],
    }


def deploy_mbr_clover_opencore(
    efi_results: Path,
    esp_mount: Path,
    log: Optional[LogFn] = None,
) -> None:
    """Deploy Clover BOOTX64 + chainload entry + OpenCore tree (MBR/CSM)."""
    _log = log or (lambda _m: None)
    gpt_opencore.deploy_gpt_opencore(efi_results, esp_mount, log=_log)

    clover_boot = paths.clover_bootx64_asset()
    if clover_boot is None:
        _log(
            "Clover BOOTX64.EFI not bundled — using OpenCore BOOTX64 as fallback. "
            "Place Clover in cocoapatcher/assets/clover/ for MBR chainload."
        )
        return

    boot_dest = esp_mount / "EFI" / "BOOT" / "BOOTX64.EFI"
    boot_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clover_boot, boot_dest)
    _log(f"Installed Clover bootloader at {boot_dest}")

    clover_dir = esp_mount / "EFI" / "CLOVER"
    clover_dir.mkdir(parents=True, exist_ok=True)
    config_path = clover_dir / "config.plist"
    with config_path.open("wb") as fh:
        plistlib.dump(_clover_config(), fh)
    _log(f"Wrote Clover config with OpenCore chainload: {config_path}")
