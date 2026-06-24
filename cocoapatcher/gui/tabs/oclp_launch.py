"""OCLP Configurator tab — flags aligned with OpenCore Legacy Patcher settings."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from cocoapatcher import paths
from cocoapatcher.core.oclp_embed import embed_oclp
from cocoapatcher.core.oclp_settings import (
    OclpSettings,
    SETTING_SECTIONS,
    SMBIOS_LEVELS,
    build_oclp_settings_nvram,
    format_settings_report,
    list_oclp_target_models,
    load_settings,
    save_settings,
    settings_path,
    tahoe_gcn_preset,
)
from cocoapatcher.gui.widgets.log_progress import ThreadSafeLog, run_in_thread


class OclpLaunchTab(ctk.CTkFrame):
    def __init__(self, master, log_panel, **kwargs):
        super().__init__(master, **kwargs)
        self._log = log_panel
        self._settings = load_settings()
        self._bool_vars: dict[str, ctk.BooleanVar] = {}
        self._widgets: dict[str, ctk.CTkBaseClass] = {}

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            top,
            text="OCLP Configurator",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(top, text="Tahoe GCN preset", width=120, command=self._load_preset).pack(
            side="right", padx=4
        )
        ctk.CTkButton(top, text="Save settings", width=100, command=self._save).pack(side="right", padx=4)

        self._summary = ctk.CTkTextbox(self, height=88)
        self._summary.pack(fill="x", padx=12, pady=4)

        scroll = ctk.CTkScrollableFrame(self, height=320)
        scroll.pack(fill="both", expand=True, padx=12, pady=4)

        self._build_target_row(scroll)
        for section, items in SETTING_SECTIONS.items():
            if section == "Target":
                continue
            ctk.CTkLabel(scroll, text=section, font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", pady=(10, 2)
            )
            for key, kind, label in items:
                self._add_field(scroll, key, kind, label)

        embed_row = ctk.CTkFrame(self, fg_color="transparent")
        embed_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(embed_row, text="USB / ESP path").pack(side="left")
        self.target_entry = ctk.CTkEntry(embed_row, placeholder_text="E:\\")
        self.target_entry.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(embed_row, text="Browse", width=72, command=self._browse).pack(side="right")
        ctk.CTkButton(self, text="Embed OCLP + PSP_new (+ settings)", command=self._embed).pack(
            anchor="w", padx=12, pady=4
        )

        doc = ctk.CTkFrame(self, fg_color="transparent")
        doc.pack(fill="x", padx=12, pady=(4, 8))
        ctk.CTkButton(
            doc,
            text="VALIDATION.md",
            width=110,
            command=lambda: webbrowser.open((paths.workspace_root() / "docs" / "VALIDATION.md").as_uri()),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            doc,
            text="OCLP Guide",
            width=100,
            command=lambda: webbrowser.open("https://dortania.github.io/OpenCore-Legacy-Patcher/"),
        ).pack(side="left")

        self._refresh_summary()

    def _build_target_row(self, parent) -> None:
        ctk.CTkLabel(parent, text="Target", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(4, 2))
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        try:
            models = list_oclp_target_models()
        except Exception:
            models = ["MacPro7,1", "iMacPro1,1"]
        combo = ctk.CTkComboBox(row, values=models, width=200)
        combo.set(self._settings.target_model if self._settings.target_model in models else models[0])
        combo.pack(side="left")
        self._widgets["target_model"] = combo
        ctk.CTkLabel(row, text="OCLP target model (patch set)", text_color="gray").pack(side="left", padx=8)

    def _add_field(self, parent, key: str, kind: str, label: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        value = getattr(self._settings, key, None)

        if kind == "bool":
            var = ctk.BooleanVar(value=bool(value))
            self._bool_vars[key] = var
            ctk.CTkCheckBox(row, text=key, variable=var, width=220).pack(side="left")
            ctk.CTkLabel(row, text=label, text_color="gray", wraplength=420, justify="left").pack(
                side="left", padx=8
            )
        elif kind == "int":
            entry = ctk.CTkEntry(row, width=60)
            entry.insert(0, str(value))
            entry.pack(side="left")
            self._widgets[key] = entry
            ctk.CTkLabel(row, text=f"{key} — {label}", text_color="gray").pack(side="left", padx=8)
        elif kind == "choice_smbios_level":
            combo = ctk.CTkComboBox(row, values=SMBIOS_LEVELS, width=140)
            combo.set(str(value) if str(value) in SMBIOS_LEVELS else "None")
            combo.pack(side="left")
            self._widgets[key] = combo
            ctk.CTkLabel(row, text=label, text_color="gray").pack(side="left", padx=8)
        else:
            entry = ctk.CTkEntry(row, width=220)
            entry.insert(0, str(value or ""))
            entry.pack(side="left")
            self._widgets[key] = entry
            ctk.CTkLabel(row, text=label, text_color="gray", wraplength=380).pack(side="left", padx=8)

    def _collect_settings(self) -> OclpSettings:
        data = {f.name: getattr(self._settings, f.name) for f in OclpSettings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        for key, var in self._bool_vars.items():
            data[key] = bool(var.get())
        if "target_model" in self._widgets:
            data["target_model"] = self._widgets["target_model"].get()
        for key, widget in self._widgets.items():
            if key == "target_model":
                continue
            if key in self._bool_vars:
                continue
            if isinstance(widget, ctk.CTkComboBox):
                data[key] = widget.get()
            else:
                raw = widget.get().strip()
                if key == "oc_timeout":
                    data[key] = int(raw) if raw.isdigit() else 5
                else:
                    data[key] = raw
        return OclpSettings(**data)

    def _refresh_summary(self) -> None:
        try:
            s = self._collect_settings()
        except Exception:
            s = self._settings
        nvram = build_oclp_settings_nvram(s)
        lines = [
            f"Settings file: {settings_path()}",
            f"Target: {s.target_model}  |  OCLP-Settings: {nvram or '(none)'}",
            f"Security: disable_cs_lv={s.disable_cs_lv} disable_amfi={s.disable_amfi} sip={s.sip_status}",
        ]
        try:
            paths.ensure_vendor_paths()
            paths.add_oclp_to_syspath()
            from opencore_legacy_patcher import constants

            c = constants.Constants()
            lines.append(f"OCLP {c.patcher_version}  PSP {c.patcher_support_pkg_version}")
            lines.append(f"PSP_new: {paths.psp_universal_binaries()}")
        except Exception as exc:
            lines.append(f"Paths: {exc}")
        self._summary.delete("0.0", "end")
        self._summary.insert("0.0", "\n".join(lines))

    def _load_preset(self) -> None:
        self._settings = tahoe_gcn_preset()
        for key, var in self._bool_vars.items():
            var.set(bool(getattr(self._settings, key, False)))
        if "target_model" in self._widgets:
            self._widgets["target_model"].set(self._settings.target_model)
        for key, widget in self._widgets.items():
            if key == "target_model":
                continue
            val = getattr(self._settings, key, "")
            if isinstance(widget, ctk.CTkComboBox):
                widget.set(str(val))
            else:
                widget.delete(0, "end")
                widget.insert(0, str(val))
        self._refresh_summary()
        self._log.append("Loaded Tahoe GCN OCLP preset.")

    def _save(self) -> None:
        try:
            self._settings = self._collect_settings()
            out = save_settings(self._settings)
            self._refresh_summary()
            self._log.append(f"OCLP settings saved: {out}")
            self._log.append(format_settings_report(self._settings))
        except Exception as exc:
            self._log.append(f"Save failed: {exc}")

    def _browse(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.target_entry.delete(0, "end")
            self.target_entry.insert(0, path)

    def _embed(self) -> None:
        target = self.target_entry.get().strip()
        if not target:
            self._log.append("Target path required.")
            return
        self._save()
        log = ThreadSafeLog(self._log, self.winfo_toplevel())

        def work():
            path = embed_oclp(Path(target), log=log)
            log(f"Embedded at {path} (includes oclp-settings.json)")

        run_in_thread(work, on_done=lambda e: self._log.append(f"Error: {e}") if e else None)
