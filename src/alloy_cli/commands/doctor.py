"""``alloy doctor`` — host environment diagnostics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core import process as _process
from alloy_cli.core.diagnose import (
    AutoFixOutcome,
    CheckResult,
    DiagnosticReport,
    apply_auto_fix,
    get_auto_fix,
)


def _print_table(console: Console, checks: tuple[CheckResult, ...]) -> None:
    table = Table(show_lines=False, header_style="bold magenta")
    table.add_column("status")
    table.add_column("name")
    table.add_column("severity")
    table.add_column("message")
    table.add_column("hint")
    table.add_column("fix")
    for c in checks:
        glyph = "✓" if c.ok else "✗"
        style = "green" if c.ok else ("red" if c.severity == "error" else "yellow")
        fix_marker = "auto" if get_auto_fix(c) is not None else "-"
        table.add_row(
            f"[{style}]{glyph}[/{style}]",
            c.name,
            c.severity,
            c.message,
            c.install_hint or "-",
            fix_marker,
        )
    console.print(table)


def _print_fix_summary(
    console: Console,
    outcomes: list[tuple[CheckResult, AutoFixOutcome]],
) -> None:
    if not outcomes:
        console.print("[dim]No auto-fixes were applicable.[/dim]")
        return
    table = Table(show_lines=False, header_style="bold magenta")
    table.add_column("name")
    table.add_column("status")
    table.add_column("log tail")
    for check, outcome in outcomes:
        glyph = "✓" if outcome.ok else "✗"
        style = "green" if outcome.ok else "red"
        tail = (outcome.log or "").splitlines()[-1] if outcome.log else "-"
        table.add_row(
            check.name,
            f"[{style}]{glyph}[/{style}]",
            tail,
        )
    console.print(table)


def _run_fixes(
    report: DiagnosticReport, project_dir: Path
) -> list[tuple[CheckResult, AutoFixOutcome]]:
    """Iterate over every fixable check and apply the registered auto-fix."""
    runner = _process.runner
    outcomes: list[tuple[CheckResult, AutoFixOutcome]] = []
    for check in report.checks:
        if get_auto_fix(check) is None:
            continue
        outcome = apply_auto_fix(check, project_root=project_dir, runner=runner)
        outcomes.append((check, outcome))
    return outcomes


@click.command("doctor", help="Diagnose the host environment for alloy-cli.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@click.option(
    "--fix",
    "auto_fix",
    is_flag=True,
    default=False,
    help="Run every available auto-fix; exits 0 only when no error rows remain.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
def doctor_command(as_json: bool, auto_fix: bool, project_dir: Path) -> None:
    report = _diagnose.run(project_dir=project_dir)
    if auto_fix:
        outcomes = _run_fixes(report, project_dir=project_dir)
        # Re-run after fixers so the final report reflects post-fix
        # state (e.g. submodule init now exposes vendors).
        report = _diagnose.run(project_dir=project_dir)
        if as_json:
            payload = report.to_dict()
            payload["auto_fixes"] = [
                {
                    "name": check.name,
                    "ok": outcome.ok,
                    "log": outcome.log,
                }
                for check, outcome in outcomes
            ]
            json.dump(payload, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            console = Console()
            _print_table(console, report.checks)
            console.print()
            console.print("[bold]Auto-fix summary[/bold]")
            _print_fix_summary(console, outcomes)
        any_failed_fix = any(not outcome.ok for _, outcome in outcomes)
        if report.has_errors or any_failed_fix:
            raise SystemExit(1)
        return

    if as_json:
        json.dump(report.to_dict(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _print_table(Console(), report.checks)
    if report.has_errors:
        raise SystemExit(1)


__all__ = ["doctor_command"]
