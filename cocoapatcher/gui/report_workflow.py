"""GUI helper: validate hardware report and open GPU fix dialog when needed."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from cocoapatcher.core.report_validation import ReportValidationError, ensure_valid_report
from cocoapatcher.gui.widgets.gpu_fix_dialog import prompt_gpu_fix_dialog


def ensure_report_valid_gui(
    report_path: Path,
    *,
    parent,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    try:
        return ensure_valid_report(
            report_path,
            parent=parent,
            log=log,
            prompt_manual=lambda path, data, items: prompt_gpu_fix_dialog(
                parent, path, data, items
            ),
        )
    except ReportValidationError as exc:
        if log:
            log(str(exc))
            log("Fix GPU entries in the report JSON or use the dialog when prompted.")
        return None
