"""Download and run Hardware Sniffer (Windows) for Report.json + ACPI dump."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from cocoapatcher import paths

SNIFFER_EXE = "Hardware-Sniffer-CLI.exe"
REPO = "lzhoang2801/Hardware-Sniffer"
GITHUB_API = f"https://api.github.com/repos/{REPO}/releases/latest"

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str, int, int], None]

_EXIT_MESSAGES = {
    3: "Error collecting hardware.",
    4: "Error generating hardware report.",
    5: "Error dumping ACPI tables.",
}


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    report_path: Path
    acpi_dir: Path


def is_supported() -> bool:
    return platform.system() == "Windows"


def sniffer_exe_path() -> Path:
    """Preferred cache location (matches OpCore-Simplify Scripts layout)."""
    opcore_scripts = paths.opcore_root() / "Scripts" / SNIFFER_EXE
    if opcore_scripts.is_file():
        return opcore_scripts
    cache = paths.sniffer_cache_dir() / SNIFFER_EXE
    return cache


def default_export_dir() -> Path:
    return paths.sysreport_dir()


def _github_latest_asset() -> tuple[str, str]:
    req = urllib.request.Request(
        GITHUB_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "cocoapatcher"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = data.get("tag_name", "latest")
    for asset in data.get("assets", []):
        if asset.get("name") == SNIFFER_EXE:
            url = asset.get("browser_download_url")
            if url:
                return tag, url
    raise FileNotFoundError(f"{SNIFFER_EXE} not found in {REPO} release {tag}")


def ensure_sniffer_exe(
    log: LogCallback = print,
    *,
    force_download: bool = False,
) -> Path:
    if not is_supported():
        raise OSError("Hardware Sniffer export is only supported on Windows.")

    dest = sniffer_exe_path()
    if dest.is_file() and not force_download:
        log(f"Using {dest}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tag, url = _github_latest_asset()
    log(f"Downloading Hardware Sniffer {tag}…")
    log(url)

    req = urllib.request.Request(url, headers={"User-Agent": "cocoapatcher"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
            shutil.copyfileobj(resp, out)
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to download {SNIFFER_EXE}. "
            f"Get it from https://github.com/{REPO}/releases/latest"
        ) from exc

    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(f"Download failed: {dest}")

    log(f"Saved {dest}")
    return dest


def export_hardware_report(
    output_dir: Path | None = None,
    *,
    log: LogCallback = print,
    progress: Optional[ProgressCallback] = None,
    force_download_sniffer: bool = False,
) -> ExportResult:
    """Run Hardware-Sniffer-CLI -e and return paths to Report.json and ACPI/."""
    if not is_supported():
        raise OSError("Hardware Sniffer export is only supported on Windows.")

    out = (output_dir or default_export_dir()).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("hardware-sniffer", 1, 3)
    exe = ensure_sniffer_exe(log, force_download=force_download_sniffer)

    if progress:
        progress("export-report", 2, 3)
    log(f"Exporting hardware report to {out}…")
    log("Run as Administrator if collection fails.")

    proc = subprocess.run(
        [str(exe), "-e", "-o", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        for line in proc.stdout.splitlines():
            log(line)
    if proc.stderr:
        for line in proc.stderr.splitlines():
            log(line)

    if proc.returncode != 0:
        detail = _EXIT_MESSAGES.get(proc.returncode, "Unknown error.")
        raise RuntimeError(
            f"Hardware Sniffer failed (exit {proc.returncode}): {detail}"
        )

    report_path = out / "Report.json"
    acpi_dir = out / "ACPI"
    if not report_path.is_file():
        raise FileNotFoundError(f"Report.json not found under {out}")

    if progress:
        progress("done", 3, 3)
    log(f"Report: {report_path}")
    if acpi_dir.is_dir():
        log(f"ACPI tables: {acpi_dir}")

    return ExportResult(output_dir=out, report_path=report_path, acpi_dir=acpi_dir)
