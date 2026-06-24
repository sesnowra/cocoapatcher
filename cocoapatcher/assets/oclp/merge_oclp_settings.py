#!/usr/bin/env python3
"""Merge embedded oclp-gui-settings.plist into OCLP global settings (macOS only)."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

TARGET = Path("/Users/Shared/.com.dortania.opencore-legacy-patcher.plist")


def main() -> int:
    if sys.platform != "darwin":
        return 0
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "oclp-gui-settings.plist"
    if not src.is_file():
        return 0
    fragment = plistlib.load(src.open("rb"))
    existing: dict = {}
    if TARGET.is_file():
        try:
            existing = plistlib.load(TARGET.open("rb"))
        except Exception:
            existing = {}
    existing.update(fragment)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    plistlib.dump(existing, TARGET.open("wb"))
    print(f"Merged OCLP settings from {src.name} → {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
