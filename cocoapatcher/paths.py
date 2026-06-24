"""Resolve vendor repository roots for mixed_tahoe workspace."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

_VENDOR_NAMES = {
    "oclp": "OpenCore-Legacy-Patcher",
    "psp_new": "PatcherSupportPkg_new",
    "opcore": "OpCore-Simplify",
}


def _frozen_exe_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _discover_workspace() -> Path:
    frozen = _frozen_exe_dir()
    if frozen is not None:
        for candidate in (frozen, frozen.parent, frozen.parent.parent):
            if (candidate / _VENDOR_NAMES["oclp"]).is_dir():
                return candidate.resolve()
        return frozen.parent.resolve()
    return Path(__file__).resolve().parent.parent.parent


def _pkg_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        if (meipass / "cocoapatcher").is_dir():
            return meipass / "cocoapatcher"
        return meipass
    return Path(__file__).resolve().parent


_PKG_ROOT = _pkg_root()
_COCOAPATCHER_ROOT = (
    _PKG_ROOT.parent
    if (_PKG_ROOT.parent / "pyproject.toml").is_file()
    else _PKG_ROOT.parent.parent
    if (_PKG_ROOT.parent.parent / "pyproject.toml").is_file()
    else _PKG_ROOT.parent
)
_DEFAULT_WORKSPACE = _discover_workspace()


def _read_vendor_paths_json() -> dict:
    candidates = [_COCOAPATCHER_ROOT / "scripts" / "vendor_paths.json"]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS) / "scripts" / "vendor_paths.json")
    for cfg in candidates:
        if cfg.is_file():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
    return {}


def workspace_root() -> Path:
    env = os.environ.get("MIXED_TAHOE_ROOT") or os.environ.get("COCOAPATCHER_WORKSPACE")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    if getattr(sys, "frozen", False):
        return _discover_workspace()
    override = _read_vendor_paths_json().get("workspace_root")
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (_COCOAPATCHER_ROOT / p).resolve()
        else:
            p = p.resolve()
        if p.is_dir():
            return p
    return _DEFAULT_WORKSPACE


def _resolve_vendor(key: str, env_var: str) -> Path:
    env = os.environ.get(env_var)
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    if not getattr(sys, "frozen", False):
        cfg = _read_vendor_paths_json()
        if key in cfg:
            p = Path(cfg[key]).expanduser()
            if not p.is_absolute():
                p = (_COCOAPATCHER_ROOT / p).resolve()
            else:
                p = p.resolve()
            if p.is_dir():
                return p
    return (workspace_root() / _VENDOR_NAMES[key]).resolve()


def oclp_root() -> Path:
    return _resolve_vendor("oclp", "OCLP_PATH")


def psp_new_root() -> Path:
    return _resolve_vendor("psp_new", "PSP_NEW_PATH")


def opcore_root() -> Path:
    return _resolve_vendor("opcore", "OPCORE_ROOT")


def psp_universal_binaries() -> Path:
    return psp_new_root() / "Universal-Binaries"


def opcore_results_dir() -> Path:
    return opcore_root() / "Results"


def sysreport_dir() -> Path:
    return opcore_root() / "SysReport"


def sniffer_cache_dir() -> Path:
    env = os.environ.get("COCOAPATCHER_SNIFFER_CACHE")
    if env:
        p = Path(env).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    if getattr(sys, "frozen", False):
        cache = workspace_root() / "cocoapatcher" / "cache"
    else:
        cache = _COCOAPATCHER_ROOT / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache.resolve()


def gibmacos_cache_dir() -> Path:
    cache = sniffer_cache_dir() / "gibMacOS"
    cache.mkdir(parents=True, exist_ok=True)
    return cache.resolve()


def installer_download_dir() -> Path:
    d = sniffer_cache_dir() / "macos-recovery"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def oclp_payloads_dir() -> Path:
    return oclp_root() / "payloads"


def clover_bootx64_asset() -> Optional[Path]:
    bundled = _PKG_ROOT / "assets" / "clover" / "BOOTX64.EFI"
    if bundled.is_file():
        return bundled
    env = os.environ.get("CLOVER_BOOTX64")
    if env and Path(env).is_file():
        return Path(env).resolve()
    return None


@dataclass(frozen=True)
class VendorPaths:
    oclp: Path
    psp_new: Path
    opcore: Path

    def items(self) -> Iterator[tuple[str, Path]]:
        yield "oclp", self.oclp
        yield "psp_new", self.psp_new
        yield "opcore", self.opcore


def ensure_vendor_paths() -> VendorPaths:
    """Return vendor paths and raise if any required root is missing."""
    roots = VendorPaths(
        oclp=oclp_root(),
        psp_new=psp_new_root(),
        opcore=opcore_root(),
    )
    missing = [name for name, path in roots.items() if not path.is_dir()]
    if missing:
        raise FileNotFoundError(
            "Missing vendor directories: "
            + ", ".join(missing)
            + f". Set MIXED_TAHOE_ROOT or per-repo env vars. Workspace: {workspace_root()}"
        )
    return roots


def _clear_scripts_frozen_stubs() -> None:
    """Drop PyInstaller PYZ stubs so OpCore Scripts resolve from opcore_root on disk."""
    import importlib

    for name in list(sys.modules):
        if name == "Scripts" or name.startswith("Scripts."):
            mod = sys.modules[name]
            mod_file = getattr(mod, "__file__", None)
            mod_path = getattr(mod, "__path__", None)
            if mod_file or mod_path:
                continue
            loader = getattr(mod, "__loader__", None)
            if loader is None or type(mod).__name__ == "MissingModule":
                del sys.modules[name]
                continue
            if type(loader).__name__ == "PyiFrozenLoader":
                try:
                    loader.get_code(name)
                except Exception:
                    del sys.modules[name]
    importlib.invalidate_caches()


def add_opcore_to_syspath() -> Path:
    root = opcore_root()
    if not (root / "Scripts").is_dir():
        return root
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    if getattr(sys, "frozen", False):
        _clear_scripts_frozen_stubs()
    return root


def add_oclp_to_syspath() -> Path:
    root = str(oclp_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    return oclp_root()
