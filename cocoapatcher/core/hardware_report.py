"""Hardware report helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_report_json(path: Path) -> dict[str, Any]:
    path = path.resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_gpu(report: dict[str, Any]) -> list[str]:
    gpus = report.get("GPU") or {}
    lines: list[str] = []
    for name, props in gpus.items():
        codename = props.get("Codename", "?")
        oclp = props.get("OCLP Compatibility")
        line = f"{name}: {codename}"
        if oclp:
            line += f" (OCLP {oclp[0]}–{oclp[-1]})"
        lines.append(line)
    return lines
