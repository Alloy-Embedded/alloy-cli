"""``alloy erase`` — flash erase with two safety gates (Wave 4).

Erases the chip's flash through the shared probe orchestrator.
Two safety gates protect the user from a typo bricking their
hardware:

1. **TTY prompt** (default): ``This will erase <total> on <chip>.
   Continue? [y/N]``.  Default N — anything other than ``y`` or
   ``yes`` (case-insensitive) raises
   ``family-toolchain-erase-aborted``.
2. **--auto / --yes**: required in non-TTY contexts (CI / pipe).
   Without one, the command refuses to run rather than blocking
   on a prompt nobody can answer.

Region aliases come from the device IR's flash bank descriptors
(when the manifest declares them).  Pass literal
``0xBASE-0xEND`` ranges when no alias exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    AlloyCliError,
    FamilyToolchainEraseAbortedError,
    FamilyToolchainEraseError,
    FamilyToolchainEraseProbeFailedError,
    FamilyToolchainEraseUnsupportedRegionError,
    FamilyToolchainProbeError,
)
from alloy_cli.core.project import PROJECT_FILE, read


def _is_stdin_tty() -> bool:
    """TTY probe broken out as a module-level helper so tests can
    monkeypatch it without having to swap ``sys.stdin``.  Mirrors
    the ``commands/new.py::_is_stdin_tty()`` helper from Wave 3.
    """
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _format_probe_label(probe: _po.ProbeIdentity) -> str:
    serial_part = f" sn={probe.serial}" if probe.serial else ""
    return f"{probe.kind}{serial_part} ({probe.vid}:{probe.pid})"


def _human_bytes(n: int) -> str:
    """Format a byte count as a short ``"32.0 KiB"`` string."""
    if n <= 0:
        return "0 B"
    value: float = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value} B"


def _render_plan(
    console: Console,
    plan: _po.ErasePlan,
    *,
    chip_label: str,
) -> None:
    """Render the erase plan as a Rich table BEFORE the prompt."""
    table = Table(
        title=f"Erase plan — {chip_label}",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("region")
    table.add_column("base")
    table.add_column("size", justify="right")
    for region in plan.regions:
        table.add_row(
            region.name,
            f"0x{region.base:08x}",
            _human_bytes(region.size),
        )
    console.print(table)


def _resolve_chip_label(project_dir: Path) -> str:
    """Best-effort: read alloy.toml + return the chip's device id."""
    toml = project_dir / PROJECT_FILE
    if not toml.exists():
        return "(unknown chip)"
    try:
        config = read(toml)
    except AlloyCliError:
        return "(unknown chip)"
    if config.chip is not None:
        return f"{config.chip.vendor}/{config.chip.family}/{config.chip.device}"
    if config.board is not None:
        return f"board={config.board.id}"
    return "(unknown chip)"


def _render_probe_error(exc: FamilyToolchainProbeError) -> str:
    """Render a typed probe error with cookbook link.  Mirrors the
    helper in ``commands/reset.py``; small enough to duplicate."""
    cookbook = f"docs/ERROR_COOKBOOK.md#{exc.error_type}"
    suffix = f"\n  See {cookbook} for recovery steps."
    if exc.error_type == "family-toolchain-probe-multiple-attached":
        from alloy_cli.core.errors import FamilyToolchainProbeMultipleAttachedError

        if isinstance(exc, FamilyToolchainProbeMultipleAttachedError) and exc.detected:
            listing = "\n".join(
                f"    • {kind} {vid}:{pid}:{serial}" for vid, pid, serial, kind in exc.detected
            )
            return f"{exc}\n\nDetected probes:\n{listing}{suffix}"
    if exc.error_type == "family-toolchain-probe-unauthorised":
        from alloy_cli.core.errors import FamilyToolchainProbeUnauthorisedError

        if isinstance(exc, FamilyToolchainProbeUnauthorisedError):
            extra = f"  Use {exc.vendor_tool!r} manually."
            if exc.install_doc_url:
                extra += f"\n  Download: {exc.install_doc_url}"
            return f"{exc}\n\n{extra}{suffix}"
    return f"{exc}{suffix}"


def _render_erase_error(exc: FamilyToolchainEraseError) -> str:
    """Render a typed erase error with cookbook link + extra context."""
    cookbook = f"docs/ERROR_COOKBOOK.md#{exc.error_type}"
    suffix = f"\n  See {cookbook} for recovery steps."
    if isinstance(exc, FamilyToolchainEraseUnsupportedRegionError) and exc.known_regions:
        listing = ", ".join(exc.known_regions)
        return f"{exc}\n\nKnown regions: {listing}{suffix}"
    if isinstance(exc, FamilyToolchainEraseProbeFailedError):
        body = exc.stderr.strip() or str(exc)
        return f"{exc}\n\nBackend output:\n{body}{suffix}"
    return f"{exc}{suffix}"


@click.command(
    "erase",
    help=(
        "Erase the chip's flash through the lockfile-pinned probe-rs.  "
        "Gated behind a TTY confirmation prompt; pass --auto / --yes to "
        "bypass in CI or non-interactive contexts.  Pass --region "
        "<name|range> to erase only part of the flash."
    ),
)
@click.option(
    "--region",
    "regions",
    metavar="NAME|0xBASE-0xEND",
    multiple=True,
    help=(
        "Region to erase.  Repeat for multiple regions.  Names "
        "(``bootloader``, ``appslot-a``, …) resolve via the device IR; "
        "``0xBASE-0xEND`` ranges pass through unchanged.  Default: "
        "chip-wide erase."
    ),
)
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt.  Required in non-TTY contexts.",
)
@click.option(
    "--yes",
    "yes",
    is_flag=True,
    default=False,
    help="Alias for --auto (matches the common `apt`/`dnf` convention).",
)
@click.option(
    "--probe",
    "probe_hint",
    metavar="VID:PID:SERIAL",
    default=None,
    help="Explicit probe selector.  Same shape as `alloy reset --probe`.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml + .alloy/toolchain.lock.",
)
def erase_command(
    regions: tuple[str, ...],
    auto: bool,
    yes: bool,
    probe_hint: str | None,
    project_dir: Path,
) -> None:
    """Erase the chip's flash via the lockfile-pinned probe-rs."""
    project_dir = project_dir.resolve()
    console = Console()
    skip_prompt = auto or yes

    # ---- Probe selection ----
    try:
        identity = _po.select_probe(hint=probe_hint, project_root=project_dir)
    except FamilyToolchainProbeError as exc:
        raise click.ClickException(_render_probe_error(exc)) from exc
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    probe = _po.real_probe_for(identity, project_root=project_dir)

    # ---- Build the plan ----
    region_args: list[str] | None = list(regions) if regions else None
    try:
        plan = _po.plan_erase(
            probe,
            regions=region_args,
            project_root=project_dir,
            all_size_bytes=0,  # backend reports actual chip-wide size
        )
    except FamilyToolchainEraseError as exc:
        raise click.ClickException(_render_erase_error(exc)) from exc
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    chip_label = _resolve_chip_label(project_dir)
    _render_plan(console, plan, chip_label=chip_label)

    # ---- Safety gates ----
    if not skip_prompt:
        if not _is_stdin_tty():
            raise click.ClickException(
                "STDIN is not a TTY; pass --auto (or --yes) to erase "
                "non-interactively.\n"
                "  See docs/ERROR_COOKBOOK.md#family-toolchain-erase-aborted "
                "for recovery steps."
            )
        size_str = _human_bytes(plan.total_bytes) if plan.total_bytes else "the chip"
        prompt = f"This will erase {size_str} on {chip_label}.  Continue?"
        if not click.confirm(prompt, default=False):
            err = FamilyToolchainEraseAbortedError("Erase aborted by user.")
            raise click.ClickException(_render_erase_error(err)) from err

    # ---- Execute ----
    try:
        report = _po.execute_erase(probe, plan)
    except FamilyToolchainEraseError as exc:
        raise click.ClickException(_render_erase_error(exc)) from exc
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    panel_body = (
        f"[bold green]✓ Flash erased.[/bold green]\n\n"
        f"Probe:       [cyan]{_format_probe_label(report.probe)}[/cyan]\n"
        f"Regions:     [cyan]{len(report.regions)}[/cyan]\n"
        f"Erased:      [cyan]{_human_bytes(report.total_bytes_erased)}[/cyan]\n"
        f"Duration:    [cyan]{report.duration_ms} ms[/cyan]"
    )
    console.print(Panel.fit(panel_body, border_style="cyan", title="alloy erase"))


__all__ = ["erase_command"]
