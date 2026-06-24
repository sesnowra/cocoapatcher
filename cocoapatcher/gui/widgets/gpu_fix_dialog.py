"""Dialog to fix invalid GPU entries in a Hardware Sniffer report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import customtkinter as ctk

from cocoapatcher.core.report_validation import (
    VALID_GPU_DEVICE_TYPES,
    VALID_GPU_MANUFACTURERS,
    GpuFixItem,
    apply_gpu_edit,
    inspect_gpu_entries,
)


class GpuFixDialog(ctk.CTkToplevel):
    """Modal editor for GPUs that fail OpCore validation."""

    def __init__(
        self,
        master,
        report_path: Path,
        report: dict[str, Any],
        items: list[GpuFixItem],
    ):
        super().__init__(master)
        self.title("Fix GPU entries in hardware report")
        self.geometry("640x520")
        self.minsize(520, 400)
        self.transient(master)
        self.grab_set()

        self._report_path = report_path
        self._report = report
        self._items = items
        self.result: dict[str, Any] | None = None

        ctk.CTkLabel(
            self,
            text="This hardware report has GPU entries OpCore cannot use.\n"
            "Remove placeholder adapters (e.g. Microsoft Basic Display) or enter values manually.",
            justify="left",
            wraplength=600,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            self,
            text=f"Report: {report_path}",
            text_color="gray",
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=16, pady=8)

        self._rows: list[dict[str, Any]] = []
        for item in items:
            self._add_gpu_row(item)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(btn_row, text="Cancel", command=self._cancel, width=100).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(
            btn_row,
            text="Save and continue",
            command=self._save,
            width=140,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window()

    def _add_gpu_row(self, item: GpuFixItem) -> None:
        frame = ctk.CTkFrame(self._scroll)
        frame.pack(fill="x", pady=8)

        ctk.CTkLabel(
            frame,
            text=item.name,
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(8, 0))

        issue_text = "; ".join(item.issues)
        if item.suggest_remove:
            issue_text += " — recommended: remove this entry"
        ctk.CTkLabel(
            frame,
            text=issue_text,
            text_color="gray",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        remove_var = ctk.BooleanVar(value=item.suggest_remove)
        ctk.CTkCheckBox(
            frame,
            text="Remove this GPU from report",
            variable=remove_var,
        ).pack(anchor="w", padx=12, pady=4)

        form = ctk.CTkFrame(frame, fg_color="transparent")
        form.pack(fill="x", padx=12, pady=(0, 12))

        mfr_default = item.props.get("Manufacturer", "")
        if mfr_default not in VALID_GPU_MANUFACTURERS:
            mfr_default = "AMD" if "amd" in item.name.casefold() else "Intel"

        ctk.CTkLabel(form, text="Manufacturer").grid(row=0, column=0, sticky="w", pady=2)
        mfr_combo = ctk.CTkComboBox(
            form,
            values=sorted(VALID_GPU_MANUFACTURERS),
            state="readonly",
            width=160,
        )
        mfr_combo.set(mfr_default)
        mfr_combo.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=2)

        ctk.CTkLabel(form, text="Codename").grid(row=1, column=0, sticky="w", pady=2)
        codename_entry = ctk.CTkEntry(form, width=280)
        codename_entry.insert(0, str(item.props.get("Codename", "") or ""))
        codename_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=2)

        dtype_default = item.props.get("Device Type", "Discrete GPU")
        if dtype_default not in VALID_GPU_DEVICE_TYPES:
            dtype_default = "Discrete GPU"

        ctk.CTkLabel(form, text="Device Type").grid(row=2, column=0, sticky="w", pady=2)
        dtype_combo = ctk.CTkComboBox(
            form,
            values=sorted(VALID_GPU_DEVICE_TYPES),
            state="readonly",
            width=160,
        )
        dtype_combo.set(dtype_default)
        dtype_combo.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=2)

        self._rows.append(
            {
                "name": item.name,
                "remove_var": remove_var,
                "mfr_combo": mfr_combo,
                "codename_entry": codename_entry,
                "dtype_combo": dtype_combo,
            }
        )

    def _cancel(self) -> None:
        self.result = None
        self.grab_release()
        self.destroy()

    def _save(self) -> None:
        data = self._report
        try:
            for row in self._rows:
                name = row["name"]
                if row["remove_var"].get():
                    data = apply_gpu_edit(data, name, remove=True)
                    continue
                data = apply_gpu_edit(
                    data,
                    name,
                    manufacturer=row["mfr_combo"].get().strip(),
                    codename=row["codename_entry"].get().strip(),
                    device_type=row["dtype_combo"].get().strip(),
                )
        except (ValueError, KeyError) as exc:
            ctk.CTkLabel(
                self,
                text=str(exc),
                text_color="#e74c3c",
            ).pack(padx=16, pady=4)
            return

        remaining = inspect_gpu_entries(data)
        if remaining:
            ctk.CTkLabel(
                self,
                text="Some GPU entries are still invalid. Check all fields or remove junk GPUs.",
                text_color="#e74c3c",
                wraplength=600,
            ).pack(padx=16, pady=4)
            return

        self.result = data
        self.grab_release()
        self.destroy()


def prompt_gpu_fix_dialog(
    parent,
    report_path: Path,
    report: dict[str, Any],
    items: list[GpuFixItem],
) -> dict[str, Any] | None:
    dialog = GpuFixDialog(parent, report_path, report, items)
    return dialog.result
