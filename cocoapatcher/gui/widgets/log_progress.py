"""Reusable GUI widgets."""

from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

import customtkinter as ctk


class LogPanel(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, height=160, **kwargs)
        self.configure(state="disabled")

    def append(self, message: str) -> None:
        self.configure(state="normal")
        self.insert("end", message.rstrip() + "\n")
        self.see("end")
        self.configure(state="disabled")


class ProgressPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.label = ctk.CTkLabel(self, text="Ready")
        self.label.pack(fill="x", padx=8, pady=(8, 4))
        self.bar = ctk.CTkProgressBar(self)
        self.bar.pack(fill="x", padx=8, pady=(0, 8))
        self.bar.set(0)

    def set_progress(self, title: str, step: int, total: int) -> None:
        self.label.configure(text=title)
        if total > 0:
            self.bar.set(min(1.0, step / total))
        else:
            self.bar.set(0)


class DiskListPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, on_select: Callable[[int], None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._buttons: list[ctk.CTkButton] = []
        self._selected: Optional[int] = None

    def set_disks(self, disks) -> None:
        for btn in self._buttons:
            btn.destroy()
        self._buttons.clear()
        for disk in disks:
            text = f"Disk {disk.index}: {disk.label} ({disk.size_gb} GB)"
            btn = ctk.CTkButton(
                self,
                text=text,
                anchor="w",
                command=lambda i=disk.index: self._select(i),
            )
            btn.pack(fill="x", padx=4, pady=2)
            self._buttons.append(btn)

    def _select(self, index: int) -> None:
        self._selected = index
        self._on_select(index)


def run_in_thread(target: Callable[[], None], on_done: Optional[Callable[[Exception | None], None]] = None):
    def _worker():
        err = None
        try:
            target()
        except Exception as exc:
            err = exc
        if on_done:
            on_done(err)

    threading.Thread(target=_worker, daemon=True).start()


class ThreadSafeLog:
    """Bridge worker-thread log lines to Tk main loop."""

    def __init__(self, panel: LogPanel, root: ctk.CTk):
        self._panel = panel
        self._root = root
        self._q: queue.Queue[str] = queue.Queue()
        self._root.after(100, self._drain)

    def __call__(self, message: str) -> None:
        self._q.put(message)

    def _drain(self) -> None:
        while True:
            try:
                msg = self._q.get_nowait()
            except queue.Empty:
                break
            self._panel.append(msg)
        self._root.after(100, self._drain)
