"""Device source modes for EFI / Easy Mode."""

from __future__ import annotations

from enum import Enum


class DeviceSource(str, Enum):
    """Where hardware + SMBIOS context comes from."""

    THIS_PC = "this_pc"
    EXTERNAL_JSON = "external_json"
    REAL_MAC = "real_mac"


DEVICE_SOURCE_LABELS: dict[DeviceSource, str] = {
    DeviceSource.THIS_PC: "This PC (Hardware Sniffer)",
    DeviceSource.EXTERNAL_JSON: "External device (Hardware Sniffer JSON)",
    DeviceSource.REAL_MAC: "Real Mac (SMBIOS picker only)",
}
