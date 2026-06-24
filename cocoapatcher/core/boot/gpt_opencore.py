"""GPT UEFI OpenCore USB layout."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

LogFn = Callable[[str], None]


def _find_boot_efi(oc_root: Path) -> Path:
    candidates = [
        oc_root / "BOOT" / "BOOTx64.efi",
        oc_root / "BOOT" / "BOOTX64.EFI",
        oc_root / "OpenCore.efi",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"OpenCore boot EFI not found under {oc_root}")


def deploy_gpt_opencore(
    efi_results: Path,
    esp_mount: Path,
    log: Optional[LogFn] = None,
) -> None:
    """Copy OpCore Results tree to ESP using standard GPT UEFI layout."""
    _log = log or (lambda _m: None)
    efi_results = efi_results.resolve()
    esp_mount = esp_mount.resolve()
    esp_mount.mkdir(parents=True, exist_ok=True)

    oc_source = efi_results / "EFI" / "OC"
    if not oc_source.is_dir():
        oc_source = efi_results / "OC"
    if not oc_source.is_dir():
        raise FileNotFoundError(f"No EFI/OC in {efi_results}")

    boot_src = _find_boot_efi(oc_source)
    boot_dest = esp_mount / "EFI" / "BOOT" / "BOOTX64.EFI"
    boot_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(boot_src, boot_dest)
    _log(f"Installed {boot_dest}")

    oc_dest = esp_mount / "EFI" / "OC"
    if oc_dest.exists():
        shutil.rmtree(oc_dest)
    shutil.copytree(oc_source, oc_dest)
    _log(f"Copied OpenCore to {oc_dest}")
