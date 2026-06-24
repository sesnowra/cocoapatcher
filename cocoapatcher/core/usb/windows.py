"""Windows removable disk enumeration and diskpart formatting."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List

from cocoapatcher.core.usb.base import DiskInfo, PartitionScheme


class WindowsDiskEnumerator:
    def list_removable_disks(self) -> List[DiskInfo]:
        disks: list[DiskInfo] = []
        try:
            import win32com.client  # type: ignore

            wmi = win32com.client.GetObject("winmgmts:")
            for item in wmi.InstancesOf("Win32_DiskDrive"):
                if not item.MediaType or "removable" not in str(item.MediaType).lower():
                    if not getattr(item, "InterfaceType", "") == "USB":
                        continue
                index = int(item.Index)
                size = int(item.Size or 0)
                model = str(item.Model or f"Disk {index}").strip()
                disks.append(
                    DiskInfo(
                        index=index,
                        label=model,
                        size_bytes=size,
                        removable=True,
                    )
                )
        except Exception:
            disks.extend(self._list_via_powershell())
        return disks

    def _list_via_powershell(self) -> List[DiskInfo]:
        script = (
            "Get-Disk | Where-Object { $_.IsRemovable -or $_.BusType -eq 'USB' } "
            "| Select-Object Number, FriendlyName, Size "
            "| ConvertTo-Json -Compress"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return []
        try:
            rows = json.loads(out.stdout)
        except json.JSONDecodeError:
            return []
        if isinstance(rows, dict):
            rows = [rows]
        disks: list[DiskInfo] = []
        for row in rows:
            index = row.get("Number")
            if index is None:
                continue
            label = str(row.get("FriendlyName") or f"Disk {index}").strip()
            size = int(row.get("Size") or 0)
            disks.append(
                DiskInfo(
                    index=int(index),
                    label=label,
                    size_bytes=size,
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
        if scheme == PartitionScheme.GPT:
            script = self._gpt_script(disk_index, label)
        else:
            script = self._mbr_script(disk_index, label)

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            tmp.write(script)
            script_path = tmp.name

        subprocess.run(
            ["diskpart", "/s", script_path],
            check=True,
            capture_output=True,
            text=True,
        )
        time.sleep(2)
        return self._assign_and_mount(disk_index)

    def _gpt_script(self, disk_index: int, label: str) -> str:
        return f"""select disk {disk_index}
clean
convert gpt
create partition primary size=512
format fs=fat32 quick label="{label}_EFI"
assign letter=S
create partition primary
format fs=exfat quick label="{label}_DATA"
assign letter=T
"""

    def _mbr_script(self, disk_index: int, label: str) -> str:
        return f"""select disk {disk_index}
clean
convert mbr
create partition primary size=512
format fs=fat32 quick label="{label}_EFI"
active
assign letter=S
create partition primary
format fs=exfat quick label="{label}_DATA"
assign letter=T
"""

    def _assign_and_mount(self, disk_index: int) -> str:
        script = (
            "Get-Volume | Where-Object { $_.FileSystemLabel -like '*_EFI' } "
            "| Select-Object DriveLetter "
            "| ConvertTo-Json -Compress"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            try:
                rows = json.loads(out.stdout)
                if isinstance(rows, dict):
                    rows = [rows]
                for row in rows:
                    letter = row.get("DriveLetter")
                    if letter:
                        return f"{letter}:\\"
            except json.JSONDecodeError:
                pass
        return "S:\\"

    @staticmethod
    def is_admin() -> bool:
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def copy_tree_to_esp(self, mount_point: str, source_efi_root: Path) -> None:
        import shutil

        dest = Path(mount_point)
        efi_src = source_efi_root / "EFI" if (source_efi_root / "EFI").is_dir() else source_efi_root
        if (efi_src / "OC").is_dir():
            shutil.copytree(efi_src, dest / "EFI", dirs_exist_ok=True)
        else:
            shutil.copytree(source_efi_root, dest, dirs_exist_ok=True)
