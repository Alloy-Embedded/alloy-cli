"""``alloy doctor`` — host environment diagnostics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core.diagnose import CheckResult


def _print_table(console: Console, checks: tuple[CheckResult, ...]) -> None:
    table = Table(show_lines=False, header_style="bold magenta")
    table.add_column("status")
    table.add_column("name")
    table.add_column("severity")
    table.add_column("message")
    table.add_column("hint")
    for c in checks:
        glyph = "✓" if c.ok else "✗"
        style = "green" if c.ok else ("red" if c.severity == "error" else "yellow")
        table.add_row(
            f"[{style}]{glyph}[/{style}]",
            c.name,
            c.severity,
            c.message,
            c.install_hint or "-",
        )
    console.print(table)


@click.command("doctor", help="Diagnose the host environment for alloy-cli.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
def doctor_command(as_json: bool, project_dir: Path) -> None:
    report = _diagnose.run(project_dir=project_dir)
    if as_json:
        json.dump(report.to_dict(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _print_table(Console(), report.checks)
    if report.has_errors:
        raise SystemExit(1)


__all__ = ["doctor_command"]
