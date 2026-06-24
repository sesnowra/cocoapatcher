"""EFI Marketplace — COCOA-EFI-STORE (staging.json via GitHub raw)."""

from __future__ import annotations

import json
import plistlib
import re
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from cocoapatcher import paths
from cocoapatcher.core.hardware_report import load_report_json
from cocoapatcher.core.macos_versions import normalize_macos_version

LogFn = Callable[[str], None]

EFI_STORE_REPO = "NiSeullent/COCOA-EFI-STORE"
EFI_STORE_DEFAULT_BRANCH = "main"
MACOS_FOLDER_KEYS = ("10.x", "11", "12", "13", "14", "15", "26")
MARKETPLACE_CATEGORIES = ("Kext", "Config", "CustomPatch")


class RefMode(str, Enum):
    OFF = "off"
    PARTIAL = "partial"
    FULL = "full"


@dataclass
class MarketplaceRefOptions:
    """Per-category reference mode for a staged EFI entry."""

    enabled: bool = False
    kext: RefMode = RefMode.OFF
    config: RefMode = RefMode.OFF
    custom_patch: RefMode = RefMode.OFF
    entry_id: str | None = None

    def auto_from_match(self, entry_id: str) -> MarketplaceRefOptions:
        return MarketplaceRefOptions(
            enabled=True,
            kext=RefMode.PARTIAL,
            config=RefMode.PARTIAL,
            custom_patch=RefMode.PARTIAL,
            entry_id=entry_id,
        )


@dataclass(frozen=True)
class MarketplaceEntry:
    id: str
    name: str
    description: str
    match: dict[str, Any]
    tree: dict[str, list[str]]
    raw_base: str
    score: int = 0


@dataclass
class DeviceFingerprint:
    manufacturer: str
    motherboard: str
    serial: str
    devices: list[dict[str, str]]
    cpu_manufacturer: str
    cpu_codename: str


def staging_raw_url(branch: str = EFI_STORE_DEFAULT_BRANCH) -> str:
    return f"https://raw.githubusercontent.com/{EFI_STORE_REPO}/{branch}/staging.json"


def macos_folder_key(macos_version: str) -> str:
    marketing = normalize_macos_version(macos_version)
    major = int(marketing.split(".", 1)[0])
    return "10.x" if major == 10 else str(major)


def _store_cache_dir() -> Path:
    cache = paths.sniffer_cache_dir() / "efi-store"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _fetch_json(url: str, *, ttl_seconds: int = 3600, force: bool = False) -> Any:
    cache = _store_cache_dir()
    safe = re.sub(r"[^\w.-]+", "_", url)[-200:]
    cache_file = cache / f"{safe}.json"
    if not force and cache_file.is_file():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl_seconds:
            return json.loads(cache_file.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": "cocoapatcher-efi-marketplace"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "cocoapatcher-efi-marketplace"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def load_staging(*, branch: str = EFI_STORE_DEFAULT_BRANCH, force: bool = False) -> dict[str, Any]:
    return _fetch_json(staging_raw_url(branch), force=force)


def extract_fingerprint(report: dict[str, Any]) -> DeviceFingerprint:
    mb = report.get("Motherboard", {})
    mb_name = str(mb.get("Name", ""))
    manufacturer = mb_name.split()[0].upper() if mb_name else ""
    cpu = report.get("CPU", {})
    serial = ""
    for key in ("System Serial", "Serial", "SerialNumber", "SystemSerialNumber"):
        if report.get(key):
            serial = str(report[key])
            break
    bios = report.get("BIOS", {})
    if not serial and isinstance(bios, dict):
        serial = str(bios.get("Serial", "") or bios.get("Serial Number", ""))

    devices: list[dict[str, str]] = []
    for gpu_name, props in (report.get("GPU") or {}).items():
        if props.get("Device Type") == "Integrated GPU":
            continue
        devices.append(
            {
                "type": "gpu",
                "name": gpu_name,
                "manufacturer": str(props.get("Manufacturer", "")),
                "device_id": str(props.get("Device ID", "")),
                "subsystem_id": str(props.get("Subsystem ID", "")),
                "codename": str(props.get("Codename", "")),
            }
        )
    for net_name, props in (report.get("Network") or {}).items():
        if props.get("Bus Type", "").startswith("PCI"):
            devices.append(
                {
                    "type": "network",
                    "name": net_name,
                    "manufacturer": "Intel" if str(props.get("Device ID", "")).startswith("8086") else "",
                    "device_id": str(props.get("Device ID", "")),
                    "subsystem_id": str(props.get("Subsystem ID", "")),
                }
            )

    return DeviceFingerprint(
        manufacturer=manufacturer,
        motherboard=mb_name,
        serial=serial.strip(),
        devices=devices,
        cpu_manufacturer=str(cpu.get("Manufacturer", "")),
        cpu_codename=str(cpu.get("Codename", "")),
    )


def _device_id_match(a: str, b: str) -> bool:
    return a.replace("-", "").lower() == b.replace("-", "").lower()


def _score_entry(fp: DeviceFingerprint, match: dict[str, Any]) -> int:
    score = 0
    serial_rule = match.get("serial")
    if serial_rule and fp.serial and str(serial_rule).lower() == fp.serial.lower():
        score += 100

    for mfr in match.get("manufacturer") or []:
        if mfr.upper() in fp.manufacturer.upper() or mfr.upper() in fp.motherboard.upper():
            score += 25

    for token in match.get("motherboard_contains") or []:
        if token.upper() in fp.motherboard.upper():
            score += 40

    cpu_rules = [d for d in match.get("devices") or [] if d.get("type") == "cpu"]
    for rule in cpu_rules:
        if rule.get("manufacturer") and rule["manufacturer"].lower() in fp.cpu_manufacturer.lower():
            score += 10
        if rule.get("codename") and rule["codename"].lower() in fp.cpu_codename.lower():
            score += 20

    for rule in match.get("devices") or []:
        dtype = rule.get("type")
        if dtype in ("cpu",):
            continue
        for dev in fp.devices:
            if dtype and dev.get("type") != dtype:
                continue
            if rule.get("manufacturer") and rule["manufacturer"].lower() not in dev.get("manufacturer", "").lower():
                continue
            if rule.get("device_id") and not _device_id_match(rule["device_id"], dev.get("device_id", "")):
                continue
            if rule.get("subsystem_id") and rule.get("subsystem_id") != dev.get("subsystem_id"):
                continue
            score += 35
            break

    return score


def list_staged_entries(
    staging: dict[str, Any] | None = None,
    *,
    branch: str = EFI_STORE_DEFAULT_BRANCH,
    force: bool = False,
) -> list[MarketplaceEntry]:
    data = staging or load_staging(branch=branch, force=force)
    raw_base = data.get("raw_base") or staging_raw_url(branch).rsplit("/", 1)[0]
    entries: list[MarketplaceEntry] = []
    for item in data.get("entries", []):
        entries.append(
            MarketplaceEntry(
                id=item["id"],
                name=item.get("name", item["id"]),
                description=item.get("description", ""),
                match=item.get("match", {}),
                tree=item.get("tree", {}),
                raw_base=raw_base,
            )
        )
    return entries


def match_entries(
    report: dict[str, Any],
    staging: dict[str, Any] | None = None,
    *,
    min_score: int = 30,
    branch: str = EFI_STORE_DEFAULT_BRANCH,
    force: bool = False,
) -> list[MarketplaceEntry]:
    fp = extract_fingerprint(report)
    ranked: list[MarketplaceEntry] = []
    for entry in list_staged_entries(staging, branch=branch, force=force):
        score = _score_entry(fp, entry.match)
        if score >= min_score:
            ranked.append(
                MarketplaceEntry(
                    id=entry.id,
                    name=entry.name,
                    description=entry.description,
                    match=entry.match,
                    tree=entry.tree,
                    raw_base=entry.raw_base,
                    score=score,
                )
            )
    ranked.sort(key=lambda e: e.score, reverse=True)
    return ranked


def best_match(
    report_path: Path,
    *,
    min_score: int = 30,
    branch: str = EFI_STORE_DEFAULT_BRANCH,
    force: bool = False,
) -> MarketplaceEntry | None:
    report = load_report_json(report_path)
    matches = match_entries(report, min_score=min_score, branch=branch, force=force)
    return matches[0] if matches else None


def _category_url(entry: MarketplaceEntry, category: str, macos_key: str, filename: str) -> str:
    return f"{entry.raw_base}/entries/{entry.id}/{category}/{macos_key}/{filename}"


def _resolve_macos_key(entry: MarketplaceEntry, category: str, macos_version: str) -> str | None:
    key = macos_folder_key(macos_version)
    supported = entry.tree.get(category, [])
    if key in supported:
        return key
    if key.startswith("10") and "10.x" in supported:
        return "10.x"
    return None


def _deep_merge_dict(base: dict, overlay: dict) -> dict:
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge_dict(base[k], v)
        else:
            base[k] = v
    return base


def _merge_plist_partial(target: Path, overlay: dict) -> None:
    data = plistlib.loads(target.read_bytes()) if target.is_file() else {}
    if not isinstance(data, dict):
        data = {}
    _deep_merge_dict(data, overlay)
    target.write_bytes(plistlib.dumps(data))


def _apply_kext(
    efi_oc: Path,
    entry: MarketplaceEntry,
    macos_key: str,
    mode: RefMode,
    log: LogFn,
) -> None:
    kexts_dir = efi_oc / "Kexts"
    kexts_dir.mkdir(parents=True, exist_ok=True)
    manifest_url = _category_url(entry, "Kext", macos_key, "manifest.json")
    try:
        manifest = _fetch_json(manifest_url, ttl_seconds=600)
    except urllib.error.HTTPError:
        log(f"Marketplace: no Kext manifest for {entry.id}/{macos_key}")
        return

    store_kext_dir = _store_cache_dir() / "entries" / entry.id / "Kext" / macos_key
    if mode == RefMode.FULL:
        if kexts_dir.exists():
            shutil.rmtree(kexts_dir)
        kexts_dir.mkdir(parents=True, exist_ok=True)

    names = manifest.get("kexts") or []
    for item in names:
        name = item if isinstance(item, str) else item.get("name")
        if not name:
            continue
        src_url = _category_url(entry, "Kext", macos_key, name)
        dest = kexts_dir / name
        try:
            if name.endswith(".kext"):
                dest.mkdir(parents=True, exist_ok=True)
                info_url = f"{src_url}/Contents/Info.plist"
                info = _fetch_bytes(info_url)
                (dest / "Contents").mkdir(parents=True, exist_ok=True)
                (dest / "Contents" / "Info.plist").write_bytes(info)
            else:
                dest.write_bytes(_fetch_bytes(src_url))
            log(f"Marketplace Kext: {name}")
        except urllib.error.HTTPError as exc:
            log(f"Marketplace Kext skip {name}: HTTP {exc.code}")


def _apply_config(
    efi_oc: Path,
    entry: MarketplaceEntry,
    macos_key: str,
    mode: RefMode,
    log: LogFn,
) -> None:
    config_path = efi_oc / "config.plist"
    manifest_url = _category_url(entry, "Config", macos_key, "manifest.json")
    try:
        manifest = _fetch_json(manifest_url, ttl_seconds=600)
    except urllib.error.HTTPError:
        log(f"Marketplace: no Config manifest for {entry.id}/{macos_key}")
        return

    plist_name = manifest.get("file") or ("config.plist" if mode == RefMode.FULL else "config.partial.plist")
    url = _category_url(entry, "Config", macos_key, plist_name)
    try:
        raw = _fetch_bytes(url)
    except urllib.error.HTTPError as exc:
        log(f"Marketplace Config skip: HTTP {exc.code}")
        return

    overlay = plistlib.loads(raw)
    if mode == RefMode.FULL:
        config_path.write_bytes(plistlib.dumps(overlay))
        log(f"Marketplace Config: full replace from {plist_name}")
    else:
        _merge_plist_partial(config_path, overlay)
        log(f"Marketplace Config: partial merge from {plist_name}")


def _apply_custom_patch(
    efi_oc: Path,
    entry: MarketplaceEntry,
    macos_key: str,
    mode: RefMode,
    log: LogFn,
) -> None:
    manifest_url = _category_url(entry, "CustomPatch", macos_key, "manifest.json")
    try:
        manifest = _fetch_json(manifest_url, ttl_seconds=600)
    except urllib.error.HTTPError:
        log(f"Marketplace: no CustomPatch manifest for {entry.id}/{macos_key}")
        return

    patch_file = manifest.get("file", "patches.json")
    url = _category_url(entry, "CustomPatch", macos_key, patch_file)
    try:
        payload = json.loads(_fetch_bytes(url).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        log(f"Marketplace CustomPatch skip: HTTP {exc.code}")
        return

    patches = payload.get("patches", payload if isinstance(payload, list) else [])
    config_path = efi_oc / "config.plist"
    data = plistlib.loads(config_path.read_bytes()) if config_path.is_file() else {}
    kernel = data.setdefault("Kernel", {})
    block = kernel.setdefault("Patch", [])
    if mode == RefMode.FULL:
        kernel["Patch"] = list(patches)
        log(f"Marketplace CustomPatch: full replace ({len(patches)} patches)")
    else:
        existing = {json.dumps(p, sort_keys=True) for p in block if isinstance(p, dict)}
        added = 0
        for p in patches:
            if isinstance(p, dict) and json.dumps(p, sort_keys=True) not in existing:
                block.append(p)
                added += 1
        log(f"Marketplace CustomPatch: partial merge (+{added} patches)")
    config_path.write_bytes(plistlib.dumps(data))


def apply_marketplace_overlay(
    efi_dir: Path,
    entry: MarketplaceEntry,
    macos_version: str,
    options: MarketplaceRefOptions,
    log: LogFn | None = None,
) -> None:
    """Apply staged EFI fragments after OpCore build."""
    out = log or print
    if not options.enabled or options.entry_id != entry.id:
        return

    oc = efi_dir / "EFI" / "OC"
    if not oc.is_dir():
        oc = efi_dir / "OC"
    if not oc.is_dir():
        raise FileNotFoundError(f"OpenCore folder not found under {efi_dir}")

    if options.kext != RefMode.OFF:
        key = _resolve_macos_key(entry, "Kext", macos_version)
        if key:
            _apply_kext(oc, entry, key, options.kext, out)

    if options.config != RefMode.OFF:
        key = _resolve_macos_key(entry, "Config", macos_version)
        if key:
            _apply_config(oc, entry, key, options.config, out)

    if options.custom_patch != RefMode.OFF:
        key = _resolve_macos_key(entry, "CustomPatch", macos_version)
        if key:
            _apply_custom_patch(oc, entry, key, options.custom_patch, out)
