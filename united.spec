# PyInstaller spec — single-file united.exe
# Run: pyinstaller united.spec

from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all

block_cipher = None
root = Path(SPECPATH)

ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")

a = Analysis(
    [str(root / "united.py")],
    pathex=[str(root)],
    binaries=ctk_binaries,
    datas=[
        (str(root / "cocoapatcher" / "assets"), "cocoapatcher/assets"),
        (str(root / "scripts" / "vendor_paths.json"), "scripts"),
        *ctk_datas,
    ],
    hiddenimports=[
        "win32com.client",
        "customtkinter",
        "PIL",
        "PIL._tkinter_finder",
        "cocoapatcher.gui.widgets.common",
        "cocoapatcher.gui.widgets.device_source",
        "cocoapatcher.gui.widgets.log_progress",
        "cocoapatcher.gui.widgets.marketplace",
        "cocoapatcher.core.opcore_static",
        *ctk_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
  # OpCore-Simplify Scripts load from disk at runtime (sibling repo); never freeze as PYZ stubs.
    excludes=[
        "Scripts",
        "Scripts.utils",
        "Scripts.smbios",
        "Scripts.compatibility_checker",
        "Scripts.datasets",
        "Scripts.datasets.os_data",
        "Scripts.datasets.mac_model_data",
        "opencore_legacy_patcher",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="united",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
