"""Embed OCLP + PatcherSupportPkg_new on USB for offline root patching."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Callable, Optional

from cocoapatcher import paths
from cocoapatcher.core.oclp_settings import export_gui_plist, load_settings, save_settings

LogFn = Callable[[str], None]

OCLP_USB_SUBDIR = Path("EFI/Utilities/OCLP")


def oclp_usb_root(esp_or_mount: Path) -> Path:
    return esp_or_mount.resolve() / OCLP_USB_SUBDIR


def embed_oclp(
    target_mount: Path,
    *,
    include_psp: bool = True,
    log: Optional[LogFn] = None,
) -> Path:
    """
    Copy OCLP source tree and PSP_new Universal-Binaries to USB.
    Returns path to embedded OCLP root on the USB.
    """
    _log = log or (lambda _m: None)
    paths.ensure_vendor_paths()
    target = oclp_usb_root(target_mount)
    payloads = target / "payloads"
    ub_dest = payloads / "Universal-Binaries"

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    oclp = paths.oclp_root()
    _log(f"Copying OCLP from {oclp}")
    exclude = {".git", "__pycache__", ".venv", "build", "dist"}
    for item in oclp.iterdir():
        if item.name in exclude:
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, dest)

    if include_psp:
        psp_ub = paths.psp_universal_binaries()
        if not psp_ub.is_dir():
            raise FileNotFoundError(f"PatcherSupportPkg_new Universal-Binaries missing: {psp_ub}")
        payloads.mkdir(parents=True, exist_ok=True)
        _log(f"Copying PSP_new Universal-Binaries from {psp_ub}")
        shutil.copytree(psp_ub, ub_dest, dirs_exist_ok=True)

    _write_launchers(target, ub_dest)
    _write_oclp_settings(target)
    _log(f"OCLP embedded at {target}")
    return target


def _write_oclp_settings(oclp_root: Path) -> None:
    settings = load_settings()
    save_settings(settings, oclp_root / "oclp-settings.json")
    export_gui_plist(settings, oclp_root / "oclp-gui-settings.plist")
    merge_src = Path(__file__).resolve().parent.parent / "assets" / "oclp" / "merge_oclp_settings.py"
    if merge_src.is_file():
        shutil.copy2(merge_src, oclp_root / "merge_oclp_settings.py")


def _write_launchers(oclp_root: Path, ub_path: Path) -> None:
    ub_str = str(ub_path).replace("\\", "/")
    run_sh = oclp_root / "Run-OCLP.command"
    run_sh.write_text(
        f"""#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export OCLP_PSP_LOCAL="{ub_str}"
export OCLP_PSP_URL=
if [ -f merge_oclp_settings.py ]; then
  python3 merge_oclp_settings.py oclp-gui-settings.plist || true
fi
exec python3 -m opencore_legacy_patcher "$@"
""",
        encoding="utf-8",
    )
    run_sh.chmod(run_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    run_bat = oclp_root / "Run-OCLP.bat"
    run_bat.write_text(
        f"""@echo off
cd /d "%~dp0"
set OCLP_PSP_LOCAL={ub_path}
set OCLP_PSP_URL=
echo OpenCore Legacy Patcher must be run from macOS after booting from this USB.
echo Embedded payloads: %OCLP_PSP_LOCAL%
pause
""",
        encoding="utf-8",
    )

    readme = oclp_root / "README-USB.txt"
    readme.write_text(
        "Boot macOS from this USB, then run Run-OCLP.command to apply root patches.\n"
        f"Local PSP: {ub_path}\n",
        encoding="utf-8",
    )
