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
from alloy_cli.core import toolchain_registry as _registry
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
    table.add_column("source")
    table.add_column("hint")
    table.add_column("fix")
    for c in checks:
        glyph = "✓" if c.ok else "✗"
        style = "green" if c.ok else ("red" if c.severity == "error" else "yellow")
        fix_marker = "auto" if get_auto_fix(c) is not None else "-"
        source = c.source or "-"
        # Vendor rows already carry the verbose label; dim them so
        # the eye lands on actionable rows first.
        if c.source and c.source.startswith("vendor"):
            source = f"[dim]{source}[/dim]"
        table.add_row(
            f"[{style}]{glyph}[/{style}]",
            c.name,
            c.severity,
            c.message,
            source,
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
    """Iterate over every fixable check and apply the registered auto-fix.

    The ``get_auto_fix(check) is None`` guard naturally skips
    vendor-source rows: vendor tools are never wired up to an
    auto-fixer, so they fall through here without an attempt.
    The regression test ``test_doctor_skips_vendor_rows_in_auto_fix``
    pins that contract.
    """
    runner = _process.runner
    outcomes: list[tuple[CheckResult, AutoFixOutcome]] = []
    for check in report.checks:
        if get_auto_fix(check) is None:
            continue
        outcome = apply_auto_fix(check, project_root=project_dir, runner=runner)
        outcomes.append((check, outcome))
    return outcomes


def _validate_family(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Click callback for ``--for``: reject unknown family ids early.

    Failing at parse-time gives the user the available options
    before any I/O happens; the run-path's own family-resolution
    error stays as a backup for the case where someone bypasses
    the CLI surface.
    """
    del ctx, param
    if value is None:
        return None
    known = _registry.known_families()
    if value in known:
        return value
    available = ", ".join(known) if known else "(none shipped)"
    raise click.BadParameter(
        f"Unknown family {value!r}.  Available families: {available}.\n"
        "Add a manifest under data/families/ — see docs/TOOLCHAIN_REGISTRY.md."
    )


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
    "--for",
    "family",
    metavar="FAMILY",
    default=None,
    callback=_validate_family,
    help=(
        "Inspect the toolchain for a specific MCU family (e.g. stm32g0, "
        "rp2040, esp32) instead of inferring it from the project's "
        "alloy.toml.  Useful before scaffolding."
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
def doctor_command(
    as_json: bool,
    auto_fix: bool,
    family: str | None,
    project_dir: Path,
) -> None:
    report = _diagnose.run(project_dir=project_dir, family=family)
    if auto_fix:
        outcomes = _run_fixes(report, project_dir=project_dir)
        # Re-run after fixers so the final report reflects post-fix
        # state (e.g. submodule init now exposes vendors).
        report = _diagnose.run(project_dir=project_dir, family=family)
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
