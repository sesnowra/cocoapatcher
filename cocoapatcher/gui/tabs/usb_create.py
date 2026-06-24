"""USB Create tab."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from cocoapatcher.core.boot import gpt_opencore, mbr_clover
from cocoapatcher.core.oclp_embed import embed_oclp
from cocoapatcher.core.usb.base import PartitionScheme, UsbMode, get_enumerator
from cocoapatcher.core.usb.windows import WindowsDiskEnumerator
from cocoapatcher.gui.widgets.common import MacosVersionPicker
from cocoapatcher.gui.widgets.log_progress import (
    ProgressPanel,
    ThreadSafeLog,
    run_in_thread,
)


class UsbCreateTab(ctk.CTkFrame):
    def __init__(self, master, log_panel, progress: ProgressPanel, **kwargs):
        super().__init__(master, **kwargs)
        self._log_panel = log_panel
        self._progress = progress

        ctk.CTkLabel(self, text="OpenCore EFI (OpCore Results folder)").pack(
            anchor="w", padx=12, pady=(12, 0)
        )
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        self.efi_entry = ctk.CTkEntry(row, placeholder_text="Path to Results/")
        self.efi_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Browse", width=80, command=self._browse_efi).pack(
            side="right"
        )

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(opts, text="Partition").grid(row=0, column=0, sticky="w")
        self.scheme_var = ctk.StringVar(value="GPT")
        self.scheme_btn = ctk.CTkSegmentedButton(
            opts, values=["GPT", "MBR"], variable=self.scheme_var
        )
        self.scheme_btn.grid(row=0, column=1, padx=8)

        ctk.CTkLabel(opts, text="Mode").grid(row=1, column=0, sticky="w", pady=8)
        self.mode_var = ctk.StringVar(value="efi-only")
        self.mode_btn = ctk.CTkSegmentedButton(
            opts,
            values=["efi-only", "macos-installer"],
            variable=self.mode_var,
            command=self._on_mode_change,
        )
        self.mode_btn.grid(row=1, column=1, padx=8)

        self.macos_picker = MacosVersionPicker(
            self,
            label="macOS version for installer USB (online recovery)",
        )
        self.macos_picker.pack(fill="x", padx=12, pady=(4, 4))

        self.embed_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self, text="Embed OCLP + PatcherSupportPkg_new", variable=self.embed_var
        ).pack(anchor="w", padx=12)

        disk_row = ctk.CTkFrame(self, fg_color="transparent")
        disk_row.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(disk_row, text="Disk index:").pack(side="left")
        self.disk_entry = ctk.CTkEntry(disk_row, width=60)
        self.disk_entry.pack(side="left", padx=8)
        ctk.CTkButton(disk_row, text="List disks", command=self._list_disks).pack(
            side="left"
        )

        if sys.platform == "win32" and not WindowsDiskEnumerator.is_admin():
            ctk.CTkLabel(
                self,
                text="Run as Administrator for USB formatting on Windows",
                text_color="orange",
            ).pack(anchor="w", padx=12)

        self._hint = ctk.CTkLabel(
            self,
            text="",
            text_color="gray",
            wraplength=760,
            justify="left",
        )
        self._hint.pack(anchor="w", padx=12, pady=4)

        ctk.CTkButton(self, text="Create USB", command=self._create).pack(
            anchor="w", padx=12, pady=12
        )
        self._on_mode_change(self.mode_var.get())

    def _on_mode_change(self, _value: str) -> None:
        installer = self.mode_var.get() == "macos-installer"
        if installer:
            self.scheme_btn.configure(state="disabled")
            self.scheme_var.set("MBR")
            if sys.platform == "darwin":
                self._hint.configure(
                    text="macOS installer: flashes via OCLP createinstallmedia, then merges OpenCore EFI."
                )
            else:
                self._hint.configure(
                    text="macOS installer (Windows): downloads Apple recovery via gibMacOS, "
                    "writes online installer USB, then deploys your OpenCore EFI. Requires 7-Zip and Admin."
                )
        else:
            self.scheme_btn.configure(state="normal")
            self._hint.configure(text="EFI-only: OpenCore boot USB without macOS installer.")

    def _browse_efi(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.efi_entry.delete(0, "end")
            self.efi_entry.insert(0, path)

    def _list_disks(self) -> None:
        try:
            enum = get_enumerator()
            lines = []
            for d in enum.list_removable_disks():
                lines.append(f"Disk {d.index}: {d.label} ({d.size_gb} GB)")
                if not self.disk_entry.get().strip():
                    self.disk_entry.insert(0, str(d.index))
            self._log_panel.append("\n".join(lines) if lines else "No removable disks found.")
        except Exception as exc:
            self._log_panel.append(f"List disks error: {exc}")

    def _create(self) -> None:
        efi = self.efi_entry.get().strip()
        disk_s = self.disk_entry.get().strip()
        macos = self.macos_picker.get_version()
        if not efi or not disk_s:
            self._log_panel.append("EFI path and disk index required.")
            return
        try:
            disk_index = int(disk_s)
        except ValueError:
            self._log_panel.append("Disk index must be an integer.")
            return

        log = ThreadSafeLog(self._log_panel, self.winfo_toplevel())
        scheme = (
            PartitionScheme.GPT
            if self.scheme_var.get() == "GPT"
            else PartitionScheme.MBR
        )
        mode = (
            UsbMode.EFI_INSTALLER
            if self.mode_var.get() == "macos-installer"
            else UsbMode.EFI_ONLY
        )

        def work():
            self.after(0, lambda: self._progress.set_progress("USB", 0, 1))
            efi_path = Path(efi)

            if mode == UsbMode.EFI_INSTALLER:
                if sys.platform == "win32":
                    from cocoapatcher.core.installer_usb_windows import (
                        create_installer_usb_windows,
                    )

                    create_installer_usb_windows(
                        efi_path,
                        disk_index,
                        macos_version=macos,
                        embed_oclp_payload=self.embed_var.get(),
                        log=log,
                    )
                else:
                    from cocoapatcher.core.installer_usb import create_installer_usb

                    create_installer_usb(
                        efi_path,
                        disk_index,
                        embed_oclp_payload=self.embed_var.get(),
                        log=log,
                    )
                return

            enum = get_enumerator()
            log(f"Formatting disk {disk_index} ({scheme.value})...")
            mount = enum.format_efi_partition(disk_index, scheme)
            mount_path = Path(mount.rstrip("\\/"))
            log(f"ESP at {mount_path}")

            if scheme == PartitionScheme.GPT:
                gpt_opencore.deploy_gpt_opencore(efi_path, mount_path, log=log)
            else:
                mbr_clover.deploy_mbr_clover_opencore(efi_path, mount_path, log=log)

            if self.embed_var.get():
                embed_oclp(mount_path, log=log)

            log("USB creation complete.")

        run_in_thread(
            work,
            on_done=lambda e: self._log_panel.append(f"Error: {e}") if e else None,
        )
