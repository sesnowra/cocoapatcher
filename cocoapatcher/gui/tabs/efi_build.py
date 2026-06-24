"""EFI Build tab (advanced)."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from cocoapatcher.core.device_compatibility import (
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


class EfiBuildTab(ctk.CTkFrame):
    def __init__(self, master, log_panel, progress: ProgressPanel, **kwargs):
        super().__init__(master, **kwargs)
        self._log_panel = log_panel
        self._progress = progress
        self._smbios_profile = SmbiosProfile.CUSTOM
        self._builder = EfiBuilder()
        self._compat = None

        ctk.CTkLabel(
            self,
            text="EFI Build (Advanced)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 0))

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
            label="Target macOS (device-compatible only)",
            on_change=self._on_macos_changed,
            choices=[],
        )
        self.macos_picker.pack(fill="x", padx=12, pady=(8, 4))

        self.show_all_smbios_var = ctk.BooleanVar(value=False)
        self._advanced_smbios = ctk.CTkFrame(self, fg_color="transparent")
        self._advanced_smbios.pack(fill="x", padx=12, pady=4)
        ctk.CTkCheckBox(
            self._advanced_smbios,
            text="Override SMBIOS manually (Macintosh picker)",
            variable=self.show_all_smbios_var,
            command=self._toggle_manual_smbios,
        ).pack(anchor="w")

        self._manual_frame = ctk.CTkFrame(self, fg_color="transparent")
        smbios_row = ctk.CTkFrame(self._manual_frame, fg_color="transparent")
        smbios_row.pack(fill="x")
        ctk.CTkLabel(smbios_row, text="SMBIOS override").pack(side="left")
        ctk.CTkButton(
            smbios_row, text="Refresh", width=72, command=self._refresh_smbios_list
        ).pack(side="right")
        self.smbios_combo = ctk.CTkComboBox(
            self._manual_frame, values=["Load device first"], state="readonly"
        )
        self.smbios_combo.pack(fill="x", pady=4)

        self.oclp_var = ctk.BooleanVar(value=False)
        self.oclp_check = ctk.CTkCheckBox(
            self,
            text="Requires OpenCore Legacy Patcher",
            variable=self.oclp_var,
        )
        self.oclp_check.pack(anchor="w", padx=12, pady=4)

        self.marketplace = MarketplacePanel(
            self,
            log=self._log_panel.append,
        )
        self.marketplace.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(self, text="Output directory (optional)").pack(anchor="w", padx=12, pady=(8, 0))
        self.output_entry = ctk.CTkEntry(self, placeholder_text="OpCore Results default")
        self.output_entry.pack(fill="x", padx=12, pady=4)

        ctk.CTkButton(self, text="Build OpenCore EFI", command=self._build).pack(
            padx=12, pady=16, anchor="w"
        )

    def _toggle_manual_smbios(self) -> None:
        if self.show_all_smbios_var.get():
            self._manual_frame.pack(fill="x", padx=12, pady=4)
            self._smbios_profile = SmbiosProfile.MACINTOSH
            self._refresh_smbios_list()
        else:
            self._manual_frame.pack_forget()
            self._smbios_profile = (
                SmbiosProfile.MACINTOSH
                if self.device_panel.source == DeviceSource.REAL_MAC
                else SmbiosProfile.CUSTOM
            )

    def _on_device_changed(self) -> None:
        if self.device_panel.source == DeviceSource.REAL_MAC:
            self._smbios_profile = SmbiosProfile.MACINTOSH
            self.show_all_smbios_var.set(False)
            self._manual_frame.pack_forget()
        elif not self.show_all_smbios_var.get():
            self._smbios_profile = SmbiosProfile.CUSTOM
        self._refresh_from_device()

    def _on_macos_changed(self) -> None:
        self._update_oclp_checkbox()
        if self._smbios_profile == SmbiosProfile.CUSTOM:
            report = self.device_panel.get_report_path()
            macos = self.macos_picker.get_version()
            if report and macos:
                try:
                    suggested = self._builder.suggest_smbios(report, macos)
                    self.device_panel.set_auto_smbios(suggested)
                except Exception:
                    pass
        if self.show_all_smbios_var.get():
            self._refresh_smbios_list()

    def _refresh_from_device(self) -> None:
        source = self.device_panel.source
        report = self.device_panel.get_report_path()
        try:
            if source == DeviceSource.REAL_MAC:
                self._compat = None
                model = self.device_panel.get_smbios_model() or "MacPro7,1"
                self.macos_picker.set_choices(self._builder.compatible_macos_for_smbios(model))
            elif report and report.is_file():
                self._compat = self._builder.analyze_device(report)
                choices = compatible_macos_choices(self._compat)
                self.macos_picker.set_choices(choices)
                if self._compat.suggested_version:
                    self.macos_picker.set_version(self._compat.suggested_version)
                macos = self.macos_picker.get_version()
                self.device_panel.set_auto_smbios(
                    self._builder.suggest_smbios(report, macos)
                )
            else:
                self._compat = None
                self.macos_picker.set_choices([])
        except DeviceCompatibilityError as exc:
            self._compat = None
            self.macos_picker.set_choices([])
            self._log_panel.append(str(exc))
        except Exception as exc:
            self._log_panel.append(f"Device analysis error: {exc}")
        self._update_oclp_checkbox()
        self.marketplace.auto_match_report(report)
        if self.show_all_smbios_var.get():
            self._refresh_smbios_list()

    def _update_oclp_checkbox(self) -> None:
        if not self._compat:
            self.oclp_var.set(False)
            self.oclp_check.configure(state="normal")
            return
        forced = oclp_required_readonly(self._compat, self.macos_picker.get_version())
        self.oclp_var.set(forced)
        self.oclp_check.configure(state="disabled" if forced else "normal")

    def _refresh_smbios_list(self) -> None:
        report = self.device_panel.get_report_path()
        macos = self.macos_picker.get_version()
        if not report or not macos:
            return
        try:
            models = self._builder.list_smbios_models(
                report,
                macos,
                compatible_only=not self.show_all_smbios_var.get(),
                form_factor_match=False,
            )
        except Exception as exc:
            self._log_panel.append(f"SMBIOS list error: {exc}")
            return
        if models:
            self.smbios_combo.configure(values=models)
            self.smbios_combo.set(models[0])

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
        report = self.device_panel.get_report_path()
        macos = self.macos_picker.get_version()
        output = self.output_entry.get().strip() or None

        if not report or not report.is_file():
            self._log_panel.append("Load or export a Hardware Sniffer report.")
            return
        if not macos or macos.startswith("("):
            self._log_panel.append("Select a compatible macOS version.")
            return

        if self.device_panel.source == DeviceSource.REAL_MAC:
            profile = SmbiosProfile.MACINTOSH
            smbios = self.device_panel.get_smbios_model()
        elif self.show_all_smbios_var.get():
            profile = SmbiosProfile.MACINTOSH
            smbios = self.smbios_combo.get().strip()
            if not smbios:
                self._log_panel.append("Select an SMBIOS override model.")
                return
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
            out = Path(output) if output else None
            result = builder.build(
                Path(report),
                macos,
                output_dir=out,
                smbios_model=smbios,
                smbios_profile=profile,
                marketplace_entry=self.marketplace.get_selected_entry(),
                marketplace_options=self.marketplace.get_options(),
            )
            log(f"Done: {result.output_dir} (SMBIOS {result.smbios_model})")

        run_in_thread(work, on_done=lambda e: self._log_panel.append(f"Error: {e}") if e else None)
