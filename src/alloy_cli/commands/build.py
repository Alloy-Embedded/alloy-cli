"""``alloy build`` Click command."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from alloy_cli.core import build as _build
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.memory import format_summary


@click.command("build", help="Build the firmware for the current project.")
@click.option(
    "--profile",
    type=click.Choice(_build.SUPPORTED_PROFILES, case_sensitive=False),
    default="debug",
    show_default=True,
    help="Build profile (maps to CMAKE_BUILD_TYPE).",
)
@click.option(
    "--clean",
    is_flag=True,
    default=False,
    help="Wipe .alloy/build before configuring.",
)
@click.option(
    "--regen",
    is_flag=True,
    default=False,
    help="Force a fresh alloy-codegen pass (ignores the .stamp cache).",
)
@click.option(
    "--no-codegen",
    "skip_codegen",
    is_flag=True,
    default=False,
    help="Skip the alloy-codegen step entirely (CI scenarios with pre-shipped headers).",
)
@click.option(
    "--project-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
def build_command(
    profile: str,
    clean: bool,
    regen: bool,
    skip_codegen: bool,
    project_dir: Path,
) -> None:
    """Configure with cmake + run ninja, then print a memory summary."""
    console = Console()

    def emit(line: str) -> None:
        console.print(line, highlight=False, markup=False)

    try:
        result = _build.run(
            project_root=project_dir,
            profile=profile,  # type: ignore[arg-type]
            clean=clean,
            regen=regen,
            skip_codegen=skip_codegen,
            on_line=emit,
        )
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.ok:
        raise click.ClickException(
            f"Build failed (codegen rc={result.codegen_returncode}, "
            f"cmake rc={result.cmake_returncode}, "
            f"ninja rc={result.build_returncode}).  See the log above."
        )

    if result.codegen_returncode is None and result.codegen_reason == "alloy-codegen-not-installed":
        codegen_label = "[yellow]codegen skipped[/yellow] (alloy-codegen not installed)"
    elif result.codegen_returncode is None or result.codegen_skipped:
        codegen_label = f"codegen [dim]skipped — {result.codegen_reason}[/dim]"
    else:
        codegen_label = "[green]codegen ran[/green]"
    console.print(
        f"[green]✓ Build OK[/green] — profile=[cyan]{result.profile}[/cyan]  {codegen_label}"
    )
    if result.elf_path is not None:
        console.print(f"  ELF: [magenta]{result.elf_path}[/magenta]")
    if result.memory is not None:
        console.print(f"  {format_summary(result.memory)}")
    elif result.elf_path is not None:
        console.print(
            "  [yellow]memory summary unavailable[/yellow] "
            "(install arm-none-eabi-size for per-section totals)."
        )


__all__ = ["build_command"]
