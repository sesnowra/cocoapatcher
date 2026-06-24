"""macOS installer USB — delegate to OCLP flash workflow."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from cocoapatcher import paths
from cocoapatcher.core.boot import gpt_opencore
from cocoapatcher.core.oclp_embed import embed_oclp

LogFn = Callable[[str], None]


class InstallerUsbError(RuntimeError):
    pass


def create_installer_usb(
    efi_results: Path,
    disk_index: int,
    installer_app: Optional[Path] = None,
    embed_oclp_payload: bool = True,
    log: Optional[LogFn] = None,
) -> None:
    """
    macOS only: flash installer via OCLP handler, then merge OpenCore EFI + OCLP embed.
    """
    _log = log or (lambda _m: None)
    if sys.platform != "darwin":
        raise InstallerUsbError(
            "EFI + Installer USB must be created on macOS. "
            "On Windows, flash the installer with Apple tools first, then use EFI-only mode."
        )

    oclp = paths.oclp_root()
    if str(oclp) not in sys.path:
        sys.path.insert(0, str(oclp))

    from opencore_legacy_patcher import constants
    from opencore_legacy_patcher.support import macos_installer_handler

    _log("Listing disks for installer flash...")
    disks = macos_installer_handler.InstallerCreation().list_disk_to_format()
    disk_id = None
    for d in disks:
        if f"disk{disk_index}" in str(d):
            disk_id = d
            break
    if disk_id is None and disks:
        disk_id = disks[0]
    if disk_id is None:
        raise InstallerUsbError("No suitable external disk found for installer flash")

    if installer_app:
        _log(f"Generating installer script for {installer_app} on {disk_id}")
        const = constants.Constants()
        script = macos_installer_handler.InstallerCreation().generate_installer_creation_script(
            const.payload_path,
            str(installer_app),
            disk_id,
        )
        _log("Run the generated script in Terminal with administrator privileges.")
        _log(script[:500] + ("..." if len(script) > 500 else ""))
    else:
        _log(
            "No installer .app specified — flash manually via OCLP GUI, "
            "then re-run cocoapatcher create-usb --mode efi-installer."
        )

    from cocoapatcher.core.usb.macos import MacOSDiskEnumerator
    from cocoapatcher.core.usb.base import PartitionScheme

    enum = MacOSDiskEnumerator()
    mount = enum.format_efi_partition(
        disk_index,
        PartitionScheme.GPT,
    )
    _log(f"ESP mounted at {mount}")
    gpt_opencore.deploy_gpt_opencore(efi_results, Path(mount), log=_log)
    if embed_oclp_payload:
        embed_oclp(Path(mount), log=_log)
