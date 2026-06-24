"""macOS target version choices (OpCore os_data + darwin normalization)."""

from __future__ import annotations

from dataclasses import dataclass

from cocoapatcher import paths


@dataclass(frozen=True)
class MacosVersionChoice:
    label: str
    """User-facing picker label, e.g. macOS Tahoe (26)."""

    version: str
    """Version string passed to OpCore / installer (e.g. 26.0.0 or 25.99.99)."""

    darwin_major: int


def _load_opcore_os_data():
    try:
        paths.add_opcore_to_syspath()
        from Scripts.datasets import os_data

        return os_data
    except (ImportError, ModuleNotFoundError):
        return None


def list_macos_version_choices(*, include_beta: bool = True) -> list[MacosVersionChoice]:
    os_data = _load_opcore_os_data()
    choices: list[MacosVersionChoice] = []
    if os_data is not None:
        for info in os_data.macos_versions:
            if not include_beta and info.release_status != "final":
                continue
            marketing = _marketing_patch(info.macos_version)
            beta = " (Beta)" if info.release_status != "final" else ""
            choices.append(
                MacosVersionChoice(
                    label=f"macOS {info.name} ({info.macos_version}){beta}",
                    version=marketing,
                    darwin_major=info.darwin_version,
                )
            )
        return choices

    from cocoapatcher.core.opcore_static import MACOS_VERSIONS

    for name, version, darwin in MACOS_VERSIONS:
        marketing = _marketing_patch(version)
        choices.append(
            MacosVersionChoice(
                label=f"macOS {name} ({version})",
                version=marketing,
                darwin_major=darwin,
            )
        )
    return choices


def default_macos_version() -> str:
    choices = list_macos_version_choices()
    return choices[-1].version if choices else "26.0.0"


def default_macos_label() -> str:
    choices = list_macos_version_choices()
    return choices[-1].label if choices else "macOS Tahoe (26)"


def normalize_macos_version(value: str) -> str:
    """Accept picker label, marketing (26.0.0), or darwin (25.99.99)."""
    raw = value.strip()
    if not raw:
        return default_macos_version()

    for choice in list_macos_version_choices():
        if raw == choice.label or raw == choice.version:
            return choice.version
        if raw.startswith(f"macOS {choice.label.split('macOS ', 1)[-1]}"):
            return choice.version

    for choice in list_macos_version_choices():
        marketing = choice.label.split("(")[-1].split(")")[0].strip()
        if raw == marketing or raw.startswith(marketing + "."):
            return choice.version

    parts = raw.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major = int(parts[0])
        if major >= 11:
            os_data = _load_opcore_os_data()
            if os_data is not None:
                for info in os_data.macos_versions:
                    if info.macos_version == str(major) or info.macos_version == raw:
                        return f"{info.darwin_version}.99.99"
            from cocoapatcher.core.opcore_static import MACOS_VERSIONS

            for _name, version, darwin in MACOS_VERSIONS:
                if version == str(major) or version == raw.split(".")[0]:
                    return f"{darwin}.99.99"
        return raw

    return raw


def _marketing_patch(macos_version: str) -> str:
    if macos_version.startswith("10."):
        return f"{macos_version}.0"
    return f"{macos_version}.0.0"


def macos_choice_labels() -> list[str]:
    return [c.label for c in list_macos_version_choices()]


def to_darwin_version(value: str) -> str:
    """Map marketing version (26.0.0) to OpCore darwin form (25.99.99)."""
    raw = normalize_macos_version(value)
    parts = raw.split(".")
    if not parts or not parts[0].isdigit():
        return raw
    major = int(parts[0])
    for choice in list_macos_version_choices():
        marketing_major = choice.version.split(".")[0]
        if marketing_major.isdigit() and int(marketing_major) == major:
            return f"{choice.darwin_major}.99.99"
        if choice.version == raw:
            return f"{choice.darwin_major}.99.99"
    if major >= 11:
        return f"{major + 9}.99.99" if major < 20 else f"{major - 1}.99.99"
    return raw


def version_from_label(label: str) -> str:
    for choice in list_macos_version_choices():
        if choice.label == label:
            return choice.version
    return normalize_macos_version(label)
