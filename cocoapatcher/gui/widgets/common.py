"""Reusable GUI widgets — macOS version picker."""

from __future__ import annotations

import customtkinter as ctk
from typing import Callable

from cocoapatcher.core.macos_versions import (
    list_macos_version_choices,
    version_from_label,
)


class MacosVersionPicker(ctk.CTkFrame):
    """Dropdown for target macOS version (device-filtered or full catalog)."""

    def __init__(
        self,
        master,
        *,
        label: str = "Target macOS version",
        on_change: Callable[[], None] | None = None,
        choices: list | None = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change
        self._choices = choices if choices is not None else list_macos_version_choices()
        labels = [c.label for c in self._choices]

        ctk.CTkLabel(self, text=label).pack(anchor="w")
        self.combo = ctk.CTkComboBox(
            self,
            values=labels or ["(no compatible versions)"],
            command=self._changed,
            state="readonly",
        )
        self.combo.pack(fill="x", pady=4)
        self._pick_default()

    def _pick_default(self) -> None:
        labels = [c.label for c in self._choices]
        if labels:
            self.combo.configure(values=labels)
            self.combo.set(labels[-1])
        else:
            self.combo.configure(values=["(no compatible versions)"])
            self.combo.set("(no compatible versions)")

    def _changed(self, _value: str) -> None:
        if self._on_change:
            self._on_change()

    def set_choices(self, choices: list) -> None:
        self._choices = choices
        self._pick_default()

    def get_version(self) -> str:
        label = self.combo.get()
        for choice in self._choices:
            if choice.label == label:
                return choice.version
        return version_from_label(label)

    def set_version(self, version: str) -> None:
        for choice in self._choices:
            if choice.version == version or version in choice.label:
                self.combo.set(choice.label)
                return
        self._pick_default()
