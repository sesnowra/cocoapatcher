"""macOS diskutil-based USB enumeration (OCLP installer patterns)."""

from __future__ import annotations

import plistlib
import re
import subprocess
from pathlib import Path
from typing import List

from cocoapatcher.core.usb.base import DiskInfo, PartitionScheme


class MacOSDiskEnumerator:
    def list_removable_disks(self) -> List[DiskInfo]:
        out = subprocess.run(
            ["diskutil", "list", "-plist", "external", "physical"],
            capture_output=True,
            check=False,
        )
        if out.returncode != 0:
            return []
        data = plistlib.loads(out.stdout)
        disks: list[DiskInfo] = []
        for ident in data.get("AllDisksAndPartitions", []):
            if ident.get("Content") != "GUID_partition_scheme" and ident.get("Content") != "FDisk_partition_scheme":
                device_id = ident.get("DeviceIdentifier", "")
                if not device_id:
                    continue
                info = self._disk_info(device_id)
                if info:
                    disks.append(info)
            else:
                device_id = ident.get("DeviceIdentifier", "")
                info = self._disk_info(device_id)
                if info:
                    disks.append(info)
        return disks

    def _disk_info(self, device_id: str) -> DiskInfo | None:
        out = subprocess.run(
            ["diskutil", "info", "-plist", device_id],
            capture_output=True,
            check=False,
        )
        if out.returncode != 0:
            return None
        info = plistlib.loads(out.stdout)
        if not info.get("RemovableMedia", False) and not info.get("External", False):
            return None
        index_match = re.search(r"disk(\d+)", device_id)
        index = int(index_match.group(1)) if index_match else 0
        return DiskInfo(
            index=index,
            label=info.get("MediaName") or device_id,
            size_bytes=int(info.get("TotalSize", 0)),
            removable=True,
            partition_scheme=info.get("Content"),
            mount_points=[info["MountPoint"]] if info.get("MountPoint") else [],
        )

    def format_efi_partition(
        self,
        disk_index: int,
        scheme: PartitionScheme,
        label: str = "COCOAPATCHER",
    ) -> str:
        device = f"/dev/disk{disk_index}"
        subprocess.run(["diskutil", "unmountDisk", "force", device], check=False)
        if scheme == PartitionScheme.GPT:
            part_map = "GPT"
        else:
            part_map = "MBRFormat"
        subprocess.run(
            [
                "diskutil",
                "partitionDisk",
                device,
                "2",
                part_map,
                "FAT32",
                f"{label}_EFI",
                "512M",
                "ExFAT",
                f"{label}_DATA",
                "R",
            ],
            check=True,
        )
        plist = subprocess.run(
            ["diskutil", "list", "-plist", device],
            capture_output=True,
            check=True,
        )
        data = plistlib.loads(plist.stdout)
        for part in data.get("Partitions", []):
            if part.get("VolumeName", "").endswith("_EFI"):
                mount = part.get("MountPoint")
                if mount:
                    return mount
                part_id = part.get("DeviceIdentifier")
                subprocess.run(["diskutil", "mount", part_id], check=True)
                info = plistlib.loads(
                    subprocess.run(
                        ["diskutil", "info", "-plist", part_id],
                        capture_output=True,
                        check=True,
                    ).stdout
                )
                return info["MountPoint"]
        raise RuntimeError(f"EFI partition not found on {device}")

    def copy_tree_to_esp(self, mount_point: str, source_efi_root: Path) -> None:
        import shutil

        dest = Path(mount_point)
        efi_src = source_efi_root / "EFI" if (source_efi_root / "EFI").is_dir() else source_efi_root
        shutil.copytree(efi_src, dest / "EFI", dirs_exist_ok=True)
