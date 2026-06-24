"""Linux USB backend (EFI-only, requires root)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List

from cocoapatcher.core.usb.base import DiskInfo, PartitionScheme


class LinuxDiskEnumerator:
    def list_removable_disks(self) -> List[DiskInfo]:
        out = subprocess.check_output(
            ["lsblk", "-J", "-o", "NAME,SIZE,RM,TYPE"],
            text=True,
        )
        data = json.loads(out)
        disks: list[DiskInfo] = []
        for idx, dev in enumerate(data.get("blockdevices", [])):
            if dev.get("type") != "disk" or dev.get("rm") != 1:
                continue
            disks.append(
                DiskInfo(
                    index=idx,
                    label=dev.get("name", "?"),
                    size_bytes=0,
                    removable=True,
                )
            )
        return disks

    def format_efi_partition(
        self,
        disk_index: int,
        scheme: PartitionScheme,
        label: str = "COCOAPATCHER",
    ) -> str:
        raise OSError(
            "Linux USB formatting is experimental — use parted manually or run on Windows/macOS."
        )
