"""CustomTkinter main window."""

from __future__ import annotations

import customtkinter as ctk

from cocoapatcher.gui.tabs.easy_mode import EasyModeTab
from cocoapatcher.gui.tabs.efi_build import EfiBuildTab
from cocoapatcher.gui.tabs.oclp_launch import OclpLaunchTab
from cocoapatcher.gui.tabs.usb_create import UsbCreateTab
from cocoapatcher.gui.widgets.log_progress import LogPanel, ProgressPanel


class CocoapatcherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("cocoapatcher — mixed_tahoe")
        self.geometry("820x680")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        self.progress = ProgressPanel(self)
        self.progress.pack(fill="x", padx=12, pady=8)

        self.log = LogPanel(self)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        tab_easy = self.tabview.add("Easy Mode")
        tab_build = self.tabview.add("EFI Build")
        tab_usb = self.tabview.add("USB Create")
        tab_oclp = self.tabview.add("OCLP Config")

        EasyModeTab(tab_easy, self.log, self.progress).pack(fill="both", expand=True)
        EfiBuildTab(tab_build, self.log, self.progress).pack(fill="both", expand=True)
        UsbCreateTab(tab_usb, self.log, self.progress).pack(fill="both", expand=True)
        OclpLaunchTab(tab_oclp, self.log).pack(fill="both", expand=True)

        self.log.append("cocoapatcher ready — Easy Mode, Build EFI, Create USB, or OCLP Config.")


def run_gui() -> None:
    CocoapatcherApp().mainloop()
