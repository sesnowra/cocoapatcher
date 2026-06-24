"""Easy Mode — device + compatible macOS + OCLP, one-click EFI build."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from cocoapatcher.core.device_compatibility import (
    DeviceCompatibility,
    DeviceCompatibilityError,
    compatible_macos_choices,
    oclp_required_readonly,
)
from cocoapatcher.core.device_source import DeviceSource
from cocoapatcher.core.efi_builder import EfiBuilder
from cocoapatcher.core.hardware_sniffer import export_hardware_report, is_supported
from cocoapatcher.core.smbios_picker import SmbiosProfile
from cocoapatcher.gui.widgets.common import MacosVersionPicker
from cocoapatcher.gui.widgets.device_source import DeviceSourcePanel
from cocoapatcher.gui.widgets.log_progress import ProgressPanel, ThreadSafeLog, run_in_thread
from cocoapatcher.gui.widgets.marketplace import MarketplacePanel


class EasyModeTab(ctk.CTkFrame):
    def __init__(self, master, log_panel, progress: ProgressPanel, **kwargs):
        super().__init__(master, **kwargs)
        self._log_panel = log_panel
        self._progress = progress
        self._builder = EfiBuilder()
        self._compat: DeviceCompatibility | None = None

        ctk.CTkLabel(
            self,
            text="Easy Mode",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 0))
        ctk.CTkLabel(
            self,
            text="Device SMBIOS is automatic. Pick external JSON or a Real Mac SMBIOS only when needed.",
            text_color="gray",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.device_panel = DeviceSourcePanel(
            self,
            on_change=self._on_device_changed,
            log=self._log_panel.append,
        )
        self.device_panel.pack(fill="x", padx=12, pady=4)
        self.device_panel.bind_export_command(self._export_report)
        self.device_panel.bind_smbios_change()

        self.macos_picker = MacosVersionPicker(
            self,
            label="Target macOS (compatible with selected device)",
            on_change=self._on_macos_changed,
            choices=[],
        )
        self.macos_picker.pack(fill="x", padx=12, pady=(8, 4))

        self._compat_label = ctk.CTkLabel(
            self,
            text="Compatibility: load a device to see supported macOS versions.",
            text_color="gray",
            wraplength=760,
            justify="left",
        )
        self._compat_label.pack(anchor="w", padx=12, pady=4)

        self.oclp_var = ctk.BooleanVar(value=False)
        self.oclp_check = ctk.CTkCheckBox(
            self,
            text="Requires OpenCore Legacy Patcher (root patches)",
            variable=self.oclp_var,
        )
        self.oclp_check.pack(anchor="w", padx=12, pady=4)

        self.marketplace = MarketplacePanel(
            self,
            on_change=lambda: None,
            log=self._log_panel.append,
        )
        self.marketplace.pack(fill="x", padx=12, pady=(4, 8))

        ctk.CTkButton(
            self,
            text="Build OpenCore EFI",
            command=self._build,
            height=36,
        ).pack(anchor="w", padx=12, pady=16)

    def _on_device_changed(self) -> None:
        self._refresh_from_device()

    def _on_macos_changed(self) -> None:
        self._update_oclp_checkbox()

    def _refresh_from_device(self) -> None:
        source = self.device_panel.source
        report = self.device_panel.get_report_path()
        macos = self.macos_picker.get_version() if self.macos_picker._choices else None

        try:
            if source == DeviceSource.REAL_MAC:
                self._compat = None
                model = self.device_panel.get_smbios_model() or "MacPro7,1"
                choices = self._builder.compatible_macos_for_smbios(model)
                self.macos_picker.set_choices(choices)
                self._compat_label.configure(
                    text=f"Real Mac SMBIOS {model}: macOS versions officially supported by this model."
                )
            elif report and report.is_file():
                self._compat = self._builder.analyze_device(report)
                choices = compatible_macos_choices(self._compat)
                self.macos_picker.set_choices(choices)
                if self._compat.suggested_version:
                    self.macos_picker.set_version(self._compat.suggested_version)
                macos = self.macos_picker.get_version()
                suggested = self._builder.suggest_smbios(report, macos)
                self.device_panel.set_auto_smbios(suggested)
                native = f"{self._compat.native_min[:2]}…{self._compat.native_max[:2]}"
                oclp = ""
                if self._compat.oclp_range:
                    oclp = f" · OCLP {self._compat.oclp_range[1][:2]}…{self._compat.oclp_range[0][:2]}"
                self._compat_label.configure(
                    text=f"Hardware compatibility (darwin): native {native}{oclp}"
                )
            else:
                self._compat = None
                self.macos_picker.set_choices([])
                self._compat_label.configure(
                    text="Export or load a Hardware Sniffer report to see compatible macOS versions."
                )
        except DeviceCompatibilityError as exc:
            self._compat = None
            self.macos_picker.set_choices([])
            self._compat_label.configure(text=str(exc))
            self._log_panel.append(str(exc))
        except Exception as exc:
            self._compat_label.configure(text=f"Error: {exc}")
            self._log_panel.append(f"Device analysis error: {exc}")
            return

        self.marketplace.auto_match_report(report)
        self._update_oclp_checkbox()

    def _update_oclp_checkbox(self) -> None:
        if not self._compat:
            self.oclp_var.set(False)
            self.oclp_check.configure(state="normal")
            return
        macos = self.macos_picker.get_version()
        forced = oclp_required_readonly(self._compat, macos)
        self.oclp_var.set(forced)
        self.oclp_check.configure(state="disabled" if forced else "normal")

    def _export_report(self) -> None:
        if not is_supported():
            self._log_panel.append("Hardware Sniffer export is only available on Windows.")
            return
        log = ThreadSafeLog(self._log_panel, self.winfo_toplevel())

        def work():
            result = export_hardware_report(
                log=log,
                progress=lambda t, s, tot: self.after(
                    0, lambda: self._progress.set_progress(t, s / max(tot, 1))
                ),
            )
            self.after(
                0,
                lambda: (
                    self.device_panel.set_report_path(result.report_path),
                    self._refresh_from_device(),
                ),
            )
            log(f"Report ready: {result.report_path}")

        run_in_thread(work, on_done=lambda e: self._log_panel.append(f"Error: {e}") if e else None)

    def _build(self) -> None:
        source = self.device_panel.source
        report = self.device_panel.get_report_path()
        macos = self.macos_picker.get_version()

        if source != DeviceSource.REAL_MAC and (not report or not report.is_file()):
            self._log_panel.append("Load or export a Hardware Sniffer report first.")
            return
        if source == DeviceSource.REAL_MAC and (not report or not report.is_file()):
            self._log_panel.append(
                "Real Mac SMBIOS mode still needs a Hardware Sniffer JSON for EFI build "
                "(your PC hardware). Browse External JSON or export This PC."
            )
            return
        if not macos or macos.startswith("("):
            self._log_panel.append("Select a compatible macOS version.")
            return

        if source == DeviceSource.REAL_MAC:
            profile = SmbiosProfile.MACINTOSH
            smbios = self.device_panel.get_smbios_model()
        else:
            profile = SmbiosProfile.CUSTOM
            smbios = self.device_panel.get_smbios_model()

        log = ThreadSafeLog(self._log_panel, self.winfo_toplevel())

        def work():
            builder = EfiBuilder(
                log=log,
                progress=lambda t, s, tot: self.after(
                    0, lambda: self._progress.set_progress(t, s / max(tot, 1))
                ),
            )
            result = builder.build(
                Path(report),
                macos,
                smbios_model=smbios,
                smbios_profile=profile,
                marketplace_entry=self.marketplace.get_selected_entry(),
                marketplace_options=self.marketplace.get_options(),
            )
            oclp = "yes" if result.needs_oclp else "no"
            log(f"Done: {result.output_dir}")
            log(f"SMBIOS {result.smbios_model} · OCLP required: {oclp}")

        run_in_thread(work, on_done=lambda e: self._log_panel.append(f"Error: {e}") if e else None)
