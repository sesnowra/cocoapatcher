# cocoapatcher

Unified **GUI + CLI** for the [mixed_tahoe](../) workspace: OpCore-Simplify EFI builds, GPT/MBR USB boot media, and OpenCore Legacy Patcher embedding with **PatcherSupportPkg_new**.

**License:** [MIT](LICENSE) — see [Open source & licenses](#license) for third-party components.

## Requirements

- Python **3.10+**
- Sibling vendor repos (not moved):
  - `../OpenCore-Legacy-Patcher`
  - `../PatcherSupportPkg_new` (canonical PSP — 12.5-25, RenderBox-25)
  - `../OpCore-Simplify`

## Install

```powershell
cd cocoapatcher
pip install -e ".[windows]"
```

On macOS/Linux omit `[windows]` or use `pip install -e .`.

## CLI

```bash
cocoapatcher-cli paths
cocoapatcher-cli export-report
cocoapatcher-cli list-smbios --report Report.json --macos 26.0.0
cocoapatcher-cli build-efi --report Report.json --macos 26.0.0 --smbios MacPro7,1
cocoapatcher-cli build-efi --report Report.json --macos 26.0.0 --smbios-profile custom
cocoapatcher-cli build-efi --report Report.json --macos 26.0.0 --output ./Results
cocoapatcher-cli create-usb --efi ./Results --disk 1 --partition GPT --mode efi-only
cocoapatcher-cli create-usb --efi ./Results --disk 1 --mode macos-installer --macos 26.0.0
cocoapatcher-cli create-usb --efi ./Results --disk 1 --partition MBR --mode efi-only
cocoapatcher-cli embed-oclp --target E:\
cocoapatcher-cli oclp-config --show
cocoapatcher-cli oclp-config --preset tahoe-gcn --save
cocoapatcher-cli gui
```

### USB modes

| Mode | Windows | macOS |
|------|---------|-------|
| `efi-only` | diskpart + OpenCore on FAT32 ESP | diskutil |
| `macos-installer` / `efi-installer` | gibMacOS recovery + online installer USB + OpenCore (7-Zip, Admin) | OCLP `createinstallmedia` flow |

### SMBIOS

| Flow | Profile | Behavior |
|------|---------|----------|
| **EFI Build** (browse `Report.json`) | `macintosh` | Pick a **Macintosh** model from compatible list (`list-smbios` / GUI combo). |
| **Hardware Sniffer** (export report) | `custom` | **Custom SMBIOS** auto-selected from sniffed hardware; changeable before build. |

OpCore writes `UpdateSMBIOSMode: Custom` in `config.plist` (standard OpCore-Simplify behavior).

### MBR + Clover

Place `BOOTX64.EFI` in `cocoapatcher/assets/clover/` (see README there). Clover chainloads `\EFI\OC\OpenCore.efi`.

## GUI

Three tabs: **EFI Build**, **USB Create**, **OCLP Config** — shared log and progress bar.

**OCLP Config** mirrors [OCLP Configurator](https://dortania.github.io/OpenCore-Legacy-Patcher/) flags (Build / Security / Root Patching / NVRAM `OCLP-Settings`). Settings save to `cocoapatcher/cache/oclp-settings.json` and ship on USB embed as `oclp-gui-settings.plist`.

**EFI Build** includes **Export Hardware Report** (Custom SMBIOS) and **Macintosh SMBIOS** picker for manual reports.

Run as **Administrator** on Windows when formatting USB drives, exporting hardware reports, or creating macOS installer USBs.

## OCLP on USB

`embed-oclp` copies OCLP + `PatcherSupportPkg_new/Universal-Binaries` to `EFI/Utilities/OCLP/` and writes launchers that set `OCLP_PSP_LOCAL`.

## Environment

| Variable | Purpose |
|----------|---------|
| `MIXED_TAHOE_ROOT` | Workspace root override |
| `OCLP_PATH` | OpenCore-Legacy-Patcher path |
| `PSP_NEW_PATH` | PatcherSupportPkg_new path |
| `OPCORE_ROOT` | OpCore-Simplify path |
| `CLOVER_BOOTX64` | MBR Clover bootloader path |

## Windows package

```powershell
.\scripts\build_windows.ps1
```

Produces `dist/cocoapatcher/` via PyInstaller. Ship `PatcherSupportPkg_new` next to the app for offline root patch.

## Validation

See [../docs/VALIDATION.md](../docs/VALIDATION.md) for R9 270X + Tahoe checklist including cocoapatcher flows.

## License

**cocoapatcher** (this repository’s application code, GUI, CLI, and packaging scripts) is distributed under the **[MIT License](LICENSE)**.

```
Copyright (c) 2025-2026 mixed_tahoe contributors
```

You may use, modify, and distribute cocoapatcher under the MIT terms above. **Third-party software** listed below is **not** covered by MIT; each component keeps its upstream license. cocoapatcher does not claim copyright over vendor trees, downloaded binaries, or payloads you place beside the app.

### Python dependencies (pip)

| Component | License | Notes |
|-----------|---------|--------|
| [Click](https://github.com/pallets/click) | BSD-3-Clause | CLI framework |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | GUI |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU (PIL) | Pulled in by CustomTkinter |
| [darkdetect](https://github.com/albertosottile/darkdetect) | BSD-3-Clause | Pulled in by CustomTkinter |
| [packaging](https://github.com/pypa/packaging) | Apache-2.0 / BSD-2-Clause | Pulled in by CustomTkinter |
| [pywin32](https://github.com/mhammond/pywin32) | PSF License | Optional `[windows]` extra |
| [Python](https://www.python.org/) | PSF License | Runtime |
| Tcl/Tk | Tcl/Tk License | GUI backend (via tkinter) |

### Build tools (not shipped in the app)

| Component | License |
|-----------|---------|
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0-only with linking exception |
| [setuptools](https://github.com/pypa/setuptools) | MIT |

### Sibling / workspace repositories (runtime integration)

These directories are **not** bundled inside cocoapatcher; the app expects them next to the [mixed_tahoe](../) workspace (or paths from environment variables).

| Component | Upstream | License |
|-----------|----------|---------|
| [OpCore-Simplify](https://github.com/lzhoang2801/OpCore-Simplify) | lzhoang2801 | BSD-3-Clause |
| [OpenCore Legacy Patcher](https://github.com/dortania/OpenCore-Legacy-Patcher) | Dortania | BSD-4-Clause (repo); see [upstream LICENSE](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/main/LICENSE.txt) and [component list](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/main/docs/LICENSE.md) |
| [PatcherSupportPkg](https://github.com/dortania/PatcherSupportPkg) / `PatcherSupportPkg_new` | Dortania et al. | Apple and third-party **binary payloads**; see [`../PatcherSupportPkg_new/LICENSE.txt`](../PatcherSupportPkg_new/LICENSE.txt) |

### Downloaded at runtime (Windows)

| Component | Upstream | License |
|-----------|----------|---------|
| [Hardware Sniffer CLI](https://github.com/lzhoang2801/Hardware-Sniffer) | lzhoang2801 | BSD-3-Clause |
| [ACPICA `acpidump.exe`](https://github.com/acpica/acpica) | Intel / ACPICA | Dual-license (see [acpica/LICENSE](https://github.com/acpica/acpica/blob/master/LICENSE)) |
| [gibMacOS](https://github.com/corpnewt/gibMacOS) (Windows installer USB) | corpnewt | Unlicense / MIT-style (see upstream) |

Hardware Sniffer is cached under `cocoapatcher/cache/` (or `OpCore-Simplify/Scripts/` when present). `acpidump.exe` is fetched by Hardware Sniffer into the SysReport workflow.

### Pulled in via OpCore-Simplify (`build-efi`)

EFI builds invoke OpCore-Simplify, which downloads and assembles third-party bootloaders and kexts (versions vary). Representative upstream licenses:

| Component | License |
|-----------|---------|
| [OpenCorePkg](https://github.com/acidanthera/OpenCorePkg) | BSD-3-Clause |
| [Lilu](https://github.com/acidanthera/Lilu), [WhateverGreen](https://github.com/acidanthera/WhateverGreen), [AirportBrcmFixup](https://github.com/acidanthera/AirportBrcmFixup), [CPUFriend](https://github.com/acidanthera/CPUFriend), [RestrictEvents](https://github.com/acidanthera/RestrictEvents), [FeatureUnlock](https://github.com/acidanthera/FeatureUnlock), [Innie](https://github.com/cdf/Innie) | BSD-3-Clause |
| [NVMeFix](https://github.com/acidanthera/NVMeFix) | GPL-2.0-only |
| [SSDTTime](https://github.com/corpnewt/SSDTTime) (ACPI tooling, vendored in OpCore) | See upstream repository |
| Additional kexts, tools, and Wi-Fi firmware | Per upstream (see OpCore download manifest and each project’s `LICENSE`) |

Full OCLP payload licensing (patches, Apple binaries, SurPlus, etc.) is documented in [OpenCore Legacy Patcher — LICENSE.md](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/main/docs/LICENSE.md).

### Optional user-supplied assets

| Component | License |
|-----------|---------|
| [Clover](https://github.com/CloverHackyColor/CloverBootloader) `BOOTX64.EFI` (MBR mode) | GPL-2.0-only (typical Clover build); **you** must supply a compliant binary — see [`cocoapatcher/assets/clover/README.md`](cocoapatcher/assets/clover/README.md) |

### Trademarks

*macOS*, *Metal*, and other Apple marks are trademarks of Apple Inc. *OpenCore*, *Hackintosh*, and project names belong to their respective owners. This project is not affiliated with Apple Inc. or Dortania.
