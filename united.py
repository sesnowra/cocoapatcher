"""
united.exe entry — GUI when launched with no args; CLI otherwise.
"""

from __future__ import annotations

import sys


def _attach_console_if_needed() -> None:
  if sys.platform != "win32":
    return
  try:
    import ctypes
    ctypes.windll.kernel32.AttachConsole(-1)  # ATTACH_PARENT_PROCESS
  except Exception:
    pass


def main() -> None:
    argv = sys.argv[1:]
    gui_launch = not argv or argv == ["gui"] or (len(argv) == 1 and argv[0] in ("-g", "--gui"))

    if not gui_launch:
        _attach_console_if_needed()
        from cocoapatcher.cli.main import cli

        cli(args=argv, prog_name="united", standalone_mode=False)
        return

    from cocoapatcher.gui.app import run_gui

    run_gui()


if __name__ == "__main__":
    main()
