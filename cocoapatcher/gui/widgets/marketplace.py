"""EFI Marketplace panel — COCOA-EFI-STORE staging + reference toggles."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from cocoapatcher.core.efi_marketplace import (
    MarketplaceEntry,
    MarketplaceRefOptions,
    RefMode,
    best_match,
    list_staged_entries,
    load_staging,
    match_entries,
    staging_raw_url,
)
from cocoapatcher.core.hardware_report import load_report_json


_REF_LABELS = {
    RefMode.OFF: "Off",
    RefMode.PARTIAL: "Partial",
    RefMode.FULL: "Full",
}


class MarketplacePanel(ctk.CTkFrame):
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
        self._entries: list[MarketplaceEntry] = []
        self._selected: MarketplaceEntry | None = None

        ctk.CTkLabel(
            self,
            text="EFI Marketplace (COCOA-EFI-STORE)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            self,
            text=staging_raw_url(),
            text_color="gray",
            font=ctk.CTkFont(size=11),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=4)
        self.enable_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            row,
            text="Use staged EFI",
            variable=self.enable_var,
            command=self._notify,
        ).pack(side="left")
        ctk.CTkButton(row, text="Refresh catalog", width=110, command=self._refresh_catalog).pack(
            side="right"
        )

        self.entry_combo = ctk.CTkComboBox(
            self,
            values=["(loading…)"],
            state="readonly",
            command=lambda _v: self._on_entry_pick(),
        )
        self.entry_combo.pack(fill="x", pady=4)

        self._match_label = ctk.CTkLabel(
            self,
            text="Auto-match when a Hardware Sniffer report is loaded.",
            text_color="gray",
            wraplength=760,
            justify="left",
        )
        self._match_label.pack(anchor="w", pady=2)

        toggles = ctk.CTkFrame(self, fg_color="transparent")
        toggles.pack(fill="x", pady=4)
        self._ref_vars: dict[str, ctk.StringVar] = {}
        for idx, (key, label) in enumerate(
            (
                ("kext", "Kext"),
                ("config", "Config"),
                ("custom_patch", "CustomPatch"),
            )
        ):
            ctk.CTkLabel(toggles, text=label).grid(row=idx, column=0, sticky="w", pady=2)
            var = ctk.StringVar(value=_REF_LABELS[RefMode.OFF])
            self._ref_vars[key] = var
            ctk.CTkSegmentedButton(
                toggles,
                values=[_REF_LABELS[m] for m in RefMode],
                variable=var,
                command=lambda _v: self._notify(),
            ).grid(row=idx, column=1, sticky="ew", padx=8, pady=2)
        toggles.grid_columnconfigure(1, weight=1)

        self._refresh_catalog()

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    def _mode_from_label(self, label: str) -> RefMode:
        for mode, text in _REF_LABELS.items():
            if text == label:
                return mode
        return RefMode.OFF

    def get_options(self) -> MarketplaceRefOptions:
        return MarketplaceRefOptions(
            enabled=self.enable_var.get() and self._selected is not None,
            kext=self._mode_from_label(self._ref_vars["kext"].get()),
            config=self._mode_from_label(self._ref_vars["config"].get()),
            custom_patch=self._mode_from_label(self._ref_vars["custom_patch"].get()),
            entry_id=self._selected.id if self._selected else None,
        )

    def get_selected_entry(self) -> MarketplaceEntry | None:
        return self._selected if self.enable_var.get() else None

    def _on_entry_pick(self) -> None:
        label = self.entry_combo.get()
        for entry in self._entries:
            if label.startswith(entry.id):
                self._selected = entry
                self.enable_var.set(True)
                self._notify()
                return

    def _refresh_catalog(self) -> None:
        try:
            staging = load_staging(force=True)
            self._entries = list_staged_entries(staging)
            labels = [f"{e.id} — {e.name}" for e in self._entries] or ["(empty catalog)"]
            self.entry_combo.configure(values=labels)
            self.entry_combo.set(labels[0])
            self._selected = self._entries[0] if self._entries else None
            self._log(f"EFI Marketplace: {len(self._entries)} staged entries loaded.")
        except Exception as exc:
            self._entries = []
            self._selected = None
            self.entry_combo.configure(values=[f"(error: {exc})"])
            self.entry_combo.set(f"(error: {exc})")
            self._log(f"EFI Marketplace load failed: {exc}")
        self._notify()

    def auto_match_report(self, report_path: Path | None) -> None:
        if not report_path or not report_path.is_file():
            self._match_label.configure(text="Auto-match when a Hardware Sniffer report is loaded.")
            return
        try:
            report = load_report_json(report_path)
            matches = match_entries(report)
            if not matches:
                self._match_label.configure(text="No staged EFI match for this device.")
                return
            best = matches[0]
            self._selected = best
            self.enable_var.set(True)
            label = f"{best.id} — {best.name}"
            values = [f"{e.id} — {e.name}" for e in self._entries]
            if label not in values:
                values.insert(0, label)
            self.entry_combo.configure(values=values)
            self.entry_combo.set(label)
            self._ref_vars["kext"].set(_REF_LABELS[RefMode.PARTIAL])
            self._ref_vars["config"].set(_REF_LABELS[RefMode.PARTIAL])
            self._ref_vars["custom_patch"].set(_REF_LABELS[RefMode.OFF])
            self._match_label.configure(
                text=f"Auto-matched: {best.name} (score {best.score}). Partial Kext/Config enabled."
            )
            self._notify()
        except Exception as exc:
            self._match_label.configure(text=f"Match error: {exc}")
