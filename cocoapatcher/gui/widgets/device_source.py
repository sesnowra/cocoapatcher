"""Device source selector (This PC / External JSON / Real Mac SMBIOS)."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from cocoapatcher.core.device_source import DEVICE_SOURCE_LABELS, DeviceSource
from cocoapatcher.core.smbios_picker import all_known_smbios_models


class DeviceSourcePanel(ctk.CTkFrame):
    """Pick device context; SMBIOS auto for PC/JSON, manual for Real Mac."""

    def __init__(
        self,
        master,
        *,
        on_change: Callable[[], None] | None = None,
        log: Callable[[str], None] | None = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change
        self._log = log or (lambda _m: None)
        self.source = DeviceSource.THIS_PC
        self.report_path: Path | None = None
        self.auto_smbios: str = ""
        self.real_mac_smbios: str = ""

        ctk.CTkLabel(self, text="Device", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=0, pady=(0, 4)
        )
        self.source_var = ctk.StringVar(value=DEVICE_SOURCE_LABELS[DeviceSource.THIS_PC])
        self.source_btn = ctk.CTkSegmentedButton(
            self,
            values=[DEVICE_SOURCE_LABELS[s] for s in DeviceSource],
            variable=self.source_var,
            command=self._on_source_change,
        )
        self.source_btn.pack(fill="x", pady=4)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", pady=4)

        self._this_pc_hint = ctk.CTkLabel(
            self.body,
            text="Export a Hardware Sniffer report on this PC. SMBIOS is chosen automatically.",
            text_color="gray",
            wraplength=760,
            justify="left",
        )
        self._export_btn = ctk.CTkButton(
            self.body, text="Export Hardware Report", command=self._export_clicked
        )

        json_row = ctk.CTkFrame(self.body, fg_color="transparent")
        self._json_row = json_row
        self._json_entry = ctk.CTkEntry(json_row, placeholder_text="Path to Report.json")
        self._json_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(json_row, text="Browse", width=80, command=self._browse_json).pack(
            side="right"
        )
        self._json_entry.bind("<KeyRelease>", lambda _e: self._load_json_path())

        self._real_mac_intro = ctk.CTkLabel(
            self.body,
            text="Real Mac model for PlatformInfo. Load Hardware Sniffer JSON below for your PC hardware (required to build EFI).",
            text_color="gray",
            wraplength=760,
            justify="left",
        )
        self._real_mac_json_label = ctk.CTkLabel(
            self.body,
            text="PC hardware report (Hardware Sniffer JSON)",
            text_color="gray",
        )
        models = all_known_smbios_models()
        self._smbios_combo = ctk.CTkComboBox(
            self.body, values=models or ["MacPro7,1"], state="readonly"
        )
        if models:
            self._smbios_combo.set("MacPro7,1" if "MacPro7,1" in models else models[0])

        self._smbios_label = ctk.CTkLabel(
            self,
            text="SMBIOS (auto): —",
            text_color="gray",
            anchor="w",
        )
        self._smbios_label.pack(anchor="w", pady=(4, 0))

        self._show_source_ui()

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    def _source_from_label(self, label: str) -> DeviceSource:
        for src, text in DEVICE_SOURCE_LABELS.items():
            if text == label:
                return src
        return DeviceSource.THIS_PC

    def _on_source_change(self, value: str) -> None:
        self.source = self._source_from_label(value)
        self._show_source_ui()
        self._notify()

    def _show_source_ui(self) -> None:
        for w in (
            self._this_pc_hint,
            self._export_btn,
            self._json_row,
            self._real_mac_intro,
            self._real_mac_json_label,
            self._smbios_combo,
        ):
            w.pack_forget()

        if self.source == DeviceSource.THIS_PC:
            self._this_pc_hint.pack(anchor="w")
            self._export_btn.pack(anchor="w", pady=4)
        elif self.source == DeviceSource.EXTERNAL_JSON:
            self._json_row.pack(fill="x")
        else:
            self._real_mac_intro.pack(anchor="w")
            self._smbios_combo.pack(fill="x", pady=4)
            self._real_mac_json_label.pack(anchor="w", pady=(8, 0))
            self._json_row.pack(fill="x", pady=4)

        self._update_smbios_label()

    def _update_smbios_label(self) -> None:
        if self.source == DeviceSource.REAL_MAC:
            model = self._smbios_combo.get().strip()
            self._smbios_label.configure(text=f"SMBIOS (Real Mac): {model or '—'}")
        elif self.auto_smbios:
            self._smbios_label.configure(text=f"SMBIOS (auto): {self.auto_smbios}")
        else:
            self._smbios_label.configure(text="SMBIOS (auto): —")

    def set_auto_smbios(self, model: str) -> None:
        self.auto_smbios = model
        self._update_smbios_label()

    def set_report_path(self, path: Path | str | None) -> None:
        if path:
            self.report_path = Path(path)
            self._json_entry.delete(0, "end")
            self._json_entry.insert(0, str(self.report_path))
        else:
            self.report_path = None
        self._notify()

    def _browse_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self._json_entry.delete(0, "end")
            self._json_entry.insert(0, path)
            self._load_json_path()

    def _load_json_path(self) -> None:
        raw = self._json_entry.get().strip()
        if not raw:
            self.report_path = None
            self._notify()
            return
        p = Path(raw)
        if p.is_file():
            self.report_path = p
            self._notify()
        else:
            self.report_path = None

    def _export_clicked(self) -> None:
        self._log("Use Export on Easy Mode or EFI Build tab (Hardware Sniffer).")

    def get_report_path(self) -> Path | None:
        return self.report_path if self.report_path and self.report_path.is_file() else None

    def get_smbios_model(self) -> str | None:
        if self.source == DeviceSource.REAL_MAC:
            return self._smbios_combo.get().strip() or None
        return self.auto_smbios or None

    def bind_export_command(self, command: Callable[[], None]) -> None:
        self._export_btn.configure(command=command)

    def bind_smbios_change(self) -> None:
        self._smbios_combo.configure(command=lambda _v: (self._update_smbios_label(), self._notify()))
