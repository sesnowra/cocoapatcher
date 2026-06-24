"""USB disk enumeration — shared types and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Protocol


class PartitionScheme(str, Enum):
    GPT = "GPT"
    MBR = "MBR"


class UsbMode(str, Enum):
    EFI_ONLY = "efi-only"
    EFI_INSTALLER = "efi-installer"


@dataclass
class DiskInfo:
    index: int
    label: str
    size_bytes: int
    removable: bool
    partition_scheme: str | None = None
    mount_points: list[str] | None = None

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024**3), 2)


class DiskEnumerator(Protocol):
    def list_removable_disks(self) -> List[DiskInfo]: ...

    def format_efi_partition(
        self,
        disk_index: int,
        scheme: PartitionScheme,
        label: str = "COCOAPATCHER",
    ) -> str:
        """Prepare disk and return mount point / drive letter for EFI partition."""
        ...


def get_enumerator():
    import sys

    if sys.platform == "win32":
        from cocoapatcher.core.usb.windows import WindowsDiskEnumerator

        return WindowsDiskEnumerator()
    if sys.platform == "darwin":
        from cocoapatcher.core.usb.macos import MacOSDiskEnumerator

        return MacOSDiskEnumerator()
    from cocoapatcher.core.usb.linux import LinuxDiskEnumerator

    return LinuxDiskEnumerator()


def get_usb_backend():
    """Alias for get_enumerator (GUI compatibility)."""
    return get_enumerator()
