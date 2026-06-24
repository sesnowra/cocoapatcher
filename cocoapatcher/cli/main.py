"""cocoapatcher CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from cocoapatcher import paths
from cocoapatcher.core.macos_versions import (
    default_macos_label,
    list_macos_version_choices,
    normalize_macos_version,
)
from cocoapatcher.core.efi_builder import EfiBuilder
from cocoapatcher.core.oclp_embed import embed_oclp
from cocoapatcher.core.usb.base import PartitionScheme, UsbMode, get_enumerator


@click.group()
@click.version_option(package_name="cocoapatcher")
def cli():
    """cocoapatcher - OpCore EFI, USB boot media, and OCLP embedding."""


def _macos_version_option(**kwargs):
    labels = [c.label for c in list_macos_version_choices()]
    return click.option(
        "--macos",
        "macos_version",
        type=click.Choice(labels, case_sensitive=False),
        default=default_macos_label(),
        help="Target macOS version",
        **kwargs,
    )


def _resolve_macos_choice(macos_version: str) -> str:
    return normalize_macos_version(macos_version)


@cli.group("efi-marketplace")
def efi_marketplace_group():
    """COCOA-EFI-STORE staging catalog (GitHub raw)."""


@efi_marketplace_group.command("list")
@click.option("--refresh", is_flag=True, help="Bypass local cache")
def efi_marketplace_list(refresh):
    """List staged EFI entries from staging.json."""
    from cocoapatcher.core.efi_marketplace import list_staged_entries, load_staging, staging_raw_url

    click.echo(staging_raw_url())
    for entry in list_staged_entries(load_staging(force=refresh)):
        click.echo(f"{entry.id}\t{entry.name}")
        for cat in ("Kext", "Config", "CustomPatch"):
            vers = entry.tree.get(cat, [])
            if vers:
                click.echo(f"  {cat}: {', '.join(vers)}")


@efi_marketplace_group.command("match")
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--refresh", is_flag=True)
def efi_marketplace_match(report_path, refresh):
    """Match hardware report to closest staged EFI."""
    from cocoapatcher.core.hardware_report import load_report_json
    from cocoapatcher.core.efi_marketplace import match_entries, load_staging

    report = load_report_json(report_path)
    staging = load_staging(force=refresh)
    matches = match_entries(report, staging)
    if not matches:
        click.echo("no match")
        return
    for entry in matches:
        click.echo(f"score={entry.score}\t{entry.id}\t{entry.name}")


@cli.command("device-compat")
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, path_type=Path))
def device_compat_cmd(report_path):
    """Show macOS versions compatible with a hardware report."""
    from cocoapatcher.core.device_compatibility import (
        analyze_hardware_report,
        compatible_macos_choices,
        needs_oclp_for_version,
    )
    from cocoapatcher.core.hardware_report import load_report_json

    profile = analyze_hardware_report(load_report_json(report_path))
    click.echo(f"native={profile.native_min}…{profile.native_max}")
    if profile.oclp_range:
        click.echo(f"oclp={profile.oclp_range[1]}…{profile.oclp_range[0]}")
    click.echo(f"suggested={profile.suggested_version}")
    for choice in compatible_macos_choices(profile):
        oclp = " oclp=1" if needs_oclp_for_version(profile, choice.version) else ""
        click.echo(f"{choice.label}\t{choice.version}{oclp}")


@cli.command("list-macos")
def list_macos_cmd():
    """List selectable macOS target versions."""
    for choice in list_macos_version_choices():
        click.echo(f"{choice.label}\t{choice.version}")


@cli.command("export-report")
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Export directory (default: OpCore-Simplify/SysReport)",
)
@click.option("--force-download", is_flag=True, help="Re-download Hardware-Sniffer-CLI.exe")
@_macos_version_option()
def export_report_cmd(output_dir, force_download, macos_version):
    """Export hardware report via Hardware Sniffer (Windows)."""
    from cocoapatcher.core.hardware_sniffer import export_hardware_report, is_supported
    from cocoapatcher.core.efi_builder import EfiBuilder

    if not is_supported():
        raise click.ClickException("Hardware Sniffer export is only supported on Windows.")

    macos_version = _resolve_macos_choice(macos_version)
    result = export_hardware_report(
        output_dir,
        log=click.echo,
        force_download_sniffer=force_download,
    )
    suggested = EfiBuilder().suggest_smbios(result.report_path, macos_version)
    click.echo(f"report={result.report_path}")
    click.echo(f"acpi={result.acpi_dir}")
    click.echo(f"suggested_smbios={suggested}")
    click.echo("Use: build-efi --smbios-profile custom --smbios <model> (or omit --smbios for auto)")


@cli.command("build-efi")
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, path_type=Path))
@_macos_version_option()
@click.option("--output", "output_dir", type=click.Path(path_type=Path), default=None)
@click.option("--smbios", default=None, help="SMBIOS model (required for macintosh profile)")
@click.option(
    "--smbios-profile",
    type=click.Choice(["macintosh", "custom"], case_sensitive=False),
    default="macintosh",
    help="macintosh=manual Mac model; custom=auto from hardware (Hardware Sniffer)",
)
def build_efi(report_path, macos_version, output_dir, smbios, smbios_profile):
    """Build OpenCore EFI via OpCore-Simplify (headless)."""
    from cocoapatcher.core.smbios_picker import SmbiosProfile

    macos_version = _resolve_macos_choice(macos_version)
    profile = SmbiosProfile(smbios_profile.lower())
    builder = EfiBuilder(log=click.echo)
    result = builder.build(
        report_path,
        macos_version,
        output_dir=output_dir,
        smbios_model=smbios,
        smbios_profile=profile,
    )
    click.echo(f"EFI written to {result.output_dir}")
    click.echo(
        f"needs_oclp={result.needs_oclp} smbios={result.smbios_model} "
        f"profile={result.smbios_profile.value}"
    )


@cli.command("list-smbios")
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, path_type=Path))
@_macos_version_option()
@click.option("--all", "show_all", is_flag=True, help="Include all Mac models (OCLP catalog)")
def list_smbios_cmd(report_path, macos_version, show_all):
    """List compatible Macintosh SMBIOS models for a hardware report."""
    macos_version = _resolve_macos_choice(macos_version)
    builder = EfiBuilder(log=click.echo)
    suggested = builder.suggest_smbios(report_path, macos_version)
    click.echo(f"suggested={suggested}")
    for name in builder.list_smbios_models(
        report_path, macos_version, compatible_only=not show_all
    ):
        click.echo(name)


@cli.command("create-usb")
@click.option("--efi", "efi_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--disk", "disk_index", required=True, type=int)
@click.option(
    "--partition",
    type=click.Choice(["GPT", "MBR"], case_sensitive=False),
    default="GPT",
)
@click.option(
    "--mode",
    type=click.Choice(["efi-only", "efi-installer", "macos-installer"], case_sensitive=False),
    default="efi-only",
)
@_macos_version_option()
@click.option("--embed-oclp/--no-embed-oclp", default=True)
@click.option("--label", default="COCOAPATCHER")
def create_usb(efi_path, disk_index, partition, mode, macos_version, embed_oclp_flag, label):
    """Format USB and deploy OpenCore (+ optional OCLP embed)."""
    macos_version = _resolve_macos_choice(macos_version)
    scheme = PartitionScheme(partition.upper())
    usb_mode = mode.lower().replace("macos-installer", "efi-installer")
    usb_mode_enum = UsbMode(usb_mode)

    if usb_mode_enum == UsbMode.EFI_INSTALLER:
        if sys.platform == "win32":
            from cocoapatcher.core.installer_usb_windows import create_installer_usb_windows

            create_installer_usb_windows(
                efi_path,
                disk_index,
                macos_version=macos_version,
                embed_oclp_payload=embed_oclp_flag,
                log=click.echo,
            )
        else:
            from cocoapatcher.core.installer_usb import create_installer_usb

            create_installer_usb(
                efi_path,
                disk_index,
                embed_oclp_payload=embed_oclp_flag,
                log=click.echo,
            )
        return

    enum = get_enumerator()
    disks = enum.list_removable_disks()
    if not any(d.index == disk_index for d in disks):
        click.echo(f"Warning: disk {disk_index} not in removable list: {[d.index for d in disks]}")

    click.echo(f"Formatting disk {disk_index} ({scheme.value}) — administrator privileges may be required.")
    mount = enum.format_efi_partition(disk_index, scheme, label=label)
    click.echo(f"ESP at {mount}")

    mount_path = Path(mount.rstrip("\\/"))
    if scheme == PartitionScheme.GPT:
        gpt_opencore.deploy_gpt_opencore(efi_path, mount_path, log=click.echo)
    else:
        mbr_clover.deploy_mbr_clover_opencore(efi_path, mount_path, log=click.echo)

    if embed_oclp_flag:
        embed_oclp(mount_path, log=click.echo)

    click.echo("USB creation complete.")


@cli.command("oclp-config")
@click.option("--show", "show_flags", is_flag=True, help="Print all OCLP flags")
@click.option("--preset", type=click.Choice(["tahoe-gcn"]), default=None)
@click.option("--save", is_flag=True, help="Write current / preset to oclp-settings.json")
def oclp_config_cmd(show_flags, preset, save):
    """View or save OCLP Configurator flags (OpenCore Legacy Patcher)."""
    from cocoapatcher.core.oclp_settings import (
        format_settings_report,
        load_settings,
        save_settings,
        settings_path,
        tahoe_gcn_preset,
    )

    settings = tahoe_gcn_preset() if preset == "tahoe-gcn" else load_settings()
    if save or preset:
        path = save_settings(settings)
        click.echo(f"Saved {path}")
    if show_flags or not (save or preset):
        click.echo(format_settings_report(settings))
    else:
        click.echo(f"Use --show to print flags. File: {settings_path()}")


@cli.command("embed-oclp")
@click.option("--target", required=True, type=click.Path(path_type=Path), help="ESP mount or OCLP folder")
@click.option("--no-psp", is_flag=True, help="Skip copying PSP_new Universal-Binaries")
def embed_oclp_cmd(target, no_psp):
    """Copy OCLP + PSP_new to USB utilities folder."""
    target = target.resolve()
    if target.name == "OCLP" or target.name.endswith("OCLP"):
        dest_root = target.parent
    else:
        dest_root = target
    path = embed_oclp(dest_root, include_psp=not no_psp, log=click.echo)
    click.echo(f"Embedded at {path}")
    click.echo(f"Set OCLP_PSP_LOCAL={path / 'payloads' / 'Universal-Binaries'}")


@cli.command("gui")
def gui_cmd():
    """Launch CustomTkinter GUI."""
    from cocoapatcher.gui.app import run_gui

    run_gui()


@cli.command("list-disks")
def list_disks_cmd():
    """List removable disks for USB creation."""
    enum = get_enumerator()
    for d in enum.list_removable_disks():
        click.echo(f"{d.index}: {d.label} ({d.size_gb} GB)")


@cli.command("paths")
def show_paths():
    """Print resolved vendor paths."""
    for name, p in paths.ensure_vendor_paths().items():
        click.echo(f"{name}: {p}")


if __name__ == "__main__":
    cli()
