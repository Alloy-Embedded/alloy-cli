"""``alloy flash`` Click command."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from alloy_cli.core import flash as _flash
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.project import PROJECT_FILE, AlloyDir, read


def _resolve_elf(project_dir: Path, elf_override: Path | None) -> Path:
    if elf_override is not None:
        return elf_override.resolve()
    layout = AlloyDir(root=project_dir)
    build_dir = layout.base / "build"
    if build_dir.is_dir():
        elfs = sorted(build_dir.rglob("*.elf"))
        if elfs:
            return elfs[0]
    raise click.ClickException("No ELF found.  Run `alloy build` first or pass --elf <path>.")


@click.command("flash", help="Flash the firmware via probe-rs.")
@click.option(
    "--probe",
    "probe_kind",
    default="auto",
    show_default=True,
    help="Probe selector: auto, jlink, stlink, picoprobe, cmsis-dap, …",
)
@click.option(
    "--target",
    default=None,
    help="Override the chip name passed to probe-rs (default: from alloy.toml).",
)
@click.option(
    "--elf",
    "elf_override",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to the firmware ELF (default: most recent build under .alloy/build/).",
)
@click.option(
    "--project-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
def flash_command(
    probe_kind: str, target: str | None, elf_override: Path | None, project_dir: Path
) -> None:
    """Auto-detect a connected probe and flash the firmware ELF."""
    console = Console()
    project_dir = project_dir.resolve()
    config = read(project_dir / PROJECT_FILE)
    elf = _resolve_elf(project_dir, elf_override)

    def emit(line: str) -> None:
        console.print(line, highlight=False, markup=False)

    try:
        result = _flash.run(
            elf=elf,
            config=config,
            probe_kind=probe_kind,
            target=target,
            on_line=emit,
        )
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.ok:
        raise click.ClickException(
            f"Flash failed (rc={result.returncode}).  See the probe-rs log above."
        )

    console.print(
        f"[green]✓ Flashed[/green] [magenta]{result.elf}[/magenta] via "
        f"[cyan]{result.probe.short}[/cyan]"
    )


__all__ = ["flash_command"]
