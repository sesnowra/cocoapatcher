"""Windows online macOS installer USB (recovery + OpenCore EFI)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from cocoapatcher import paths
from cocoapatcher.core.boot import gpt_opencore
from cocoapatcher.core.oclp_embed import embed_oclp

LogFn = Callable[[str], None]

GIBMACOS_REPO = "https://github.com/corpnewt/gibMacOS.git"
DD_URL = "https://github.com/corpnewt/gibMacOS/files/4573241/ddrelease64.exe.zip"
RECOVERY_SUFFIXES = (
    "recoveryhdupdate.pkg",
    "recoveryhdmetadmg.pkg",
    "basesystem.dmg",
    "recoveryimage.dmg",
)


class InstallerUsbWindowsError(RuntimeError):
    pass


def _log_or_print(log: Optional[LogFn], msg: str) -> None:
    (log or print)(msg)


def _require_admin() -> None:
    try:
        import ctypes

        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise InstallerUsbWindowsError("Administrator privileges required for USB installer creation.")
    except InstallerUsbWindowsError:
        raise
    except Exception as exc:
        raise InstallerUsbWindowsError("Could not verify administrator privileges.") from exc


def _find_7z() -> Path:
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "7-Zip" / "7z.exe",
    ):
        if candidate.is_file():
            return candidate
    raise InstallerUsbWindowsError(
        "7-Zip not found. Install 7-Zip (https://www.7-zip.org/) and retry."
    )


def _run(cmd: list[str], *, cwd: Path | None = None, log: Optional[LogFn] = None) -> subprocess.CompletedProcess:
    _log_or_print(log, f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _macos_version_arg(macos_version: str) -> str:
    major = macos_version.split(".", 1)[0]
    if major.isdigit() and int(major) >= 11:
        return major
    names = {
        "10.15": "catalina",
        "10.14": "mojave",
        "10.13": "high sierra",
        "11": "big sur",
        "12": "monterey",
        "13": "ventura",
        "14": "sonoma",
        "15": "sequoia",
        "26": "tahoe",
    }
    return names.get(macos_version.rsplit(".", 1)[0] if macos_version.count(".") >= 2 else macos_version, major)


def ensure_gibmacos(log: Optional[LogFn] = None) -> Path:
    root = paths.gibmacos_cache_dir()
    gib = root / "gibMacOS.py"
    if gib.is_file():
        return root
    if root.exists() and any(root.iterdir()):
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    _log_or_print(log, "Cloning gibMacOS…")
    proc = _run(["git", "clone", "--depth", "1", GIBMACOS_REPO, str(root)], log=log)
    if proc.returncode != 0 or not gib.is_file():
        raise InstallerUsbWindowsError(
            f"Failed to clone gibMacOS: {proc.stderr or proc.stdout}"
        )
    return root


def ensure_dd(gib_root: Path, log: Optional[LogFn] = None) -> Path:
    scripts = gib_root / "Scripts"
    dd_exe = scripts / "ddrelease64.exe"
    if dd_exe.is_file():
        return dd_exe
    scripts.mkdir(parents=True, exist_ok=True)
    _log_or_print(log, "Downloading ddrelease64…")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "dd.zip"
        req = urllib.request.Request(DD_URL, headers={"User-Agent": "cocoapatcher"})
        with urllib.request.urlopen(req, timeout=120) as resp, zpath.open("wb") as out:
            shutil.copyfileobj(resp, out)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(scripts)
    if not dd_exe.is_file():
        raise InstallerUsbWindowsError("ddrelease64.exe download failed.")
    return dd_exe


def download_recovery_packages(
    macos_version: str,
    download_dir: Path | None = None,
    log: Optional[LogFn] = None,
) -> Path:
    gib_root = ensure_gibmacos(log)
    dest = (download_dir or paths.installer_download_dir()).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    version_arg = _macos_version_arg(macos_version)
    _log_or_print(log, f"Downloading recovery packages for macOS {macos_version} ({version_arg})…")
    proc = _run(
        [
            sys.executable,
            str(gib_root / "gibMacOS.py"),
            "-r",
            "-v",
            version_arg,
            "-o",
            str(dest),
            "--no-interactive",
        ],
        cwd=gib_root,
        log=log,
    )
    if proc.stdout:
        for line in proc.stdout.splitlines():
            _log_or_print(log, line)
    if proc.returncode != 0:
        raise InstallerUsbWindowsError(
            f"gibMacOS recovery download failed:\n{proc.stderr or proc.stdout}"
        )
    hits = [
        p
        for p in dest.rglob("*")
        if p.is_file() and p.name.lower().endswith(RECOVERY_SUFFIXES)
    ]
    if not hits:
        raise InstallerUsbWindowsError(
            f"No recovery packages found under {dest}. Check network and macOS version."
        )
    return hits[0].parent


def _extract_hfs_image(recovery_dir: Path, seven_zip: Path, log: Optional[LogFn] = None) -> Path:
    pkg = next(
        (
            p
            for p in recovery_dir.iterdir()
            if p.is_file() and p.name.lower().endswith(RECOVERY_SUFFIXES)
        ),
        None,
    )
    if pkg is None:
        raise InstallerUsbWindowsError(f"No recovery package in {recovery_dir}")

    if pkg.suffix.lower() == ".hfs":
        return pkg

    work = Path(tempfile.mkdtemp(prefix="cocoapatcher-hfs-"))
    try:
        _log_or_print(log, f"Extracting recovery image from {pkg.name}…")
        if pkg.name.lower().endswith(".dmg"):
            proc = _run([str(seven_zip), "e", "-tdmg", str(pkg), "*.hfs"], cwd=work, log=log)
        else:
            proc = _run([str(seven_zip), "e", "-txar", str(pkg), "*.dmg"], cwd=work, log=log)
            if proc.returncode != 0:
                raise InstallerUsbWindowsError(proc.stderr or proc.stdout)
            proc = _run([str(seven_zip), "e", "*.dmg", "*/Base*.dmg"], cwd=work, log=log)
            if proc.returncode != 0:
                raise InstallerUsbWindowsError(proc.stderr or proc.stdout)
            bases = list(work.glob("Base*.dmg"))
            if not bases:
                raise InstallerUsbWindowsError("BaseSystem.dmg not found in recovery package.")
            proc = _run([str(seven_zip), "e", "-tdmg", str(bases[0]), "*.hfs"], cwd=work, log=log)
        if proc.returncode != 0:
            raise InstallerUsbWindowsError(proc.stderr or proc.stdout)
        hfs_files = list(work.glob("*.hfs"))
        if not hfs_files:
            raise InstallerUsbWindowsError("Failed to extract .hfs recovery image.")
        final = recovery_dir / hfs_files[0].name
        shutil.copy2(hfs_files[0], final)
        return final
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _diskpart_mbr_installer_layout(disk_index: int, log: Optional[LogFn] = None) -> None:
    script = f"""select disk {disk_index}
clean
convert mbr
create partition primary size=200
format quick fs=fat32 label=BOOT
active
create partition primary
select partition 2
set id=AB
select partition 1
assign
"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
        tmp.write(script)
        script_path = tmp.name
    try:
        proc = _run(["diskpart", "/s", script_path], log=log)
        if proc.returncode != 0:
            raise InstallerUsbWindowsError(proc.stderr or proc.stdout or "diskpart failed")
    finally:
        Path(script_path).unlink(missing_ok=True)
    time.sleep(2)


def _dd_to_partition2(disk_index: int, hfs_image: Path, dd_exe: Path, log: Optional[LogFn] = None) -> None:
    target = fr"\\.\PhysicalDrive{disk_index}"
    part2 = fr"\\?\Device\Harddisk{disk_index}\Partition2"
    _log_or_print(log, f"Writing recovery image to {part2} (this may take several minutes)…")
    proc = _run(
        [str(dd_exe), f"if={hfs_image}", f"of={part2}", "bs=8M", "--progress"],
        log=log,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "error" in out.lower():
        raise InstallerUsbWindowsError(f"dd failed:\n{out}")


def _find_boot_volume(log: Optional[LogFn] = None) -> Path:
    for _ in range(10):
        proc = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Volume -FileSystemLabel BOOT -ErrorAction SilentlyContinue "
                "| Select-Object -ExpandProperty DriveLetter",
            ],
            log=None,
        )
        letter = (proc.stdout or "").strip()
        if letter and re.fullmatch(r"[A-Z]", letter):
            mount = Path(f"{letter}:\\")
            _log_or_print(log, f"BOOT volume at {mount}")
            return mount
        time.sleep(1)
    raise InstallerUsbWindowsError("Could not locate FAT32 BOOT volume after diskpart.")


def create_installer_usb_windows(
    efi_results: Path,
    disk_index: int,
    macos_version: str = "26.0.0",
    *,
    recovery_dir: Path | None = None,
    embed_oclp_payload: bool = True,
    log: Optional[LogFn] = None,
) -> None:
    """
    Create an online macOS installer USB on Windows:
    MBR layout (200MB FAT32 BOOT + recovery partition), gibMacOS recovery, custom OpenCore EFI.
    """
    if sys.platform != "win32":
        raise InstallerUsbWindowsError("Windows installer USB creation is only supported on Windows.")

    _require_admin()
    seven_zip = _find_7z()
    gib_root = ensure_gibmacos(log)
    dd_exe = ensure_dd(gib_root, log)

    pkg_dir = recovery_dir or download_recovery_packages(macos_version, log=log)
    hfs_image = _extract_hfs_image(pkg_dir, seven_zip, log=log)

    _log_or_print(log, f"Formatting disk {disk_index} for macOS installer (MBR)…")
    _diskpart_mbr_installer_layout(disk_index, log=log)

    _dd_to_partition2(disk_index, hfs_image, dd_exe, log=log)

    boot_mount = _find_boot_volume(log)
    _log_or_print(log, "Deploying OpenCore EFI to BOOT partition…")
    gpt_opencore.deploy_gpt_opencore(efi_results.resolve(), boot_mount, log=log)
    if embed_oclp_payload:
        embed_oclp(boot_mount, log=log)

    _log_or_print(log, "macOS installer USB ready (online recovery). Boot and connect Ethernet/Wi‑Fi in installer.")
