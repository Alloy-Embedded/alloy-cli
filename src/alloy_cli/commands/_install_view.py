"""Shared CLI rendering for toolchain install plans + reports.

Wave-3 entry points (``alloy new`` post-scaffold, ``alloy doctor --fix``,
``alloy setup``) all dispatch through
:func:`alloy_cli.core.toolchain_orchestrator.install_family` and want
to render the same Rich table / progress lines.  This module owns
that UI vocabulary so the entry points stay thin.

Pure rendering — never resolves a manifest, never spawns a download.
The caller resolves the plan via
:func:`alloy_cli.core.toolchain_orchestrator.plan_install` and the
report via :func:`install_family`.
"""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.table import Table

from alloy_cli.core.toolchain_orchestrator import (
    InstallEvent,
    InstallPlanItem,
    InstallReport,
    ToolDownloaded,
    ToolFailed,
    ToolInstalled,
    ToolSkippedHostUnsupported,
    ToolSkippedVendor,
    ToolStarted,
)
from alloy_cli.core.toolchain_registry import FamilyManifest


def human_bytes(n: int) -> str:
    """Format a byte count as a short ``"12.3 MiB"`` string."""
    if n <= 0:
        return "?"
    value: float = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value} B"


def render_install_plan(
    console: Console,
    manifest: FamilyManifest,
    plan: list[InstallPlanItem],
    *,
    title: str | None = None,
) -> None:
    """Render the plan as a Rich table — one row per tool.

    The vendor + unsupported-host rows render as ``skip`` so the user
    can see the full surface before answering Y/N.
    """
    table = Table(
        title=title or f"Install plan — {manifest.family_id}",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("tool")
    table.add_column("tier")
    table.add_column("version")
    table.add_column("source")
    table.add_column("status")
    table.add_column("size", justify="right")
    table.add_column("url / hint")
    for item in plan:
        if item.is_actionable and item.artifact is not None:
            size = human_bytes(item.artifact.size_bytes or 0) if item.artifact.size_bytes else "?"
            table.add_row(
                item.tool.tool,
                item.tier,
                item.artifact.version,
                item.artifact.source,
                "[green]install[/green]",
                size,
                item.artifact.url,
            )
        else:
            table.add_row(
                item.tool.tool,
                item.tier,
                item.tool.version,
                item.tool.source,
                "[yellow]skip[/yellow]",
                "-",
                f"[dim]{item.skip_reason}[/dim]",
            )
    console.print(table)


def render_install_summary(console: Console, report: InstallReport) -> None:
    """One-or-two-line status after the walker finishes.

    Always prints the totals line; when the lockfile changed, names
    the path; when vendor tools were skipped, lists each with its
    install_doc URL so the user knows what's still missing.
    """
    if report.failed_count:
        console.print(
            f"\n[red]✗ {report.failed_count} tool(s) failed[/red]; "
            f"[green]{report.installed_count}[/green] installed, "
            f"{human_bytes(report.total_bytes_downloaded)} downloaded."
        )
    else:
        console.print(
            f"\n[bold green]✓ Toolchain ready.[/bold green] "
            f"{report.installed_count} tool(s), "
            f"{human_bytes(report.total_bytes_downloaded)} downloaded."
        )
    if report.lockfile_updated and report.lockfile_path is not None:
        console.print(f"[green]✓ Updated[/green] {report.lockfile_path}")
    for vendor in report.vendor_skipped:
        line = f"  [dim]vendor[/dim] {vendor.tool}@{vendor.version}"
        if vendor.install_doc_url:
            line += f" — see {vendor.install_doc_url}"
        console.print(line)


def make_event_logger(console: Console) -> Callable[[InstallEvent], None]:
    """Return an ``on_event`` callback that prints one line per event.

    Suitable for non-Textual contexts (the CLI commands).  The TUI
    plugs its own callback that pumps events into a Textual message
    queue instead.
    """

    def _on(event: InstallEvent) -> None:
        if isinstance(event, ToolStarted):
            console.print(
                f"  [cyan]→[/cyan] {event.tool}@{event.version} "
                f"({event.source}, {human_bytes(event.size_bytes or 0)})"
            )
        elif isinstance(event, ToolDownloaded):
            console.print(f"    [dim]downloaded {human_bytes(event.bytes_downloaded)}[/dim]")
        elif isinstance(event, ToolInstalled):
            verb = "skipped (already installed)" if event.skipped else "installed"
            console.print(f"  [green]✓[/green] {event.tool}@{event.version} {verb}")
        elif isinstance(event, ToolSkippedVendor):
            line = (
                f"  [yellow]·[/yellow] {event.tool}@{event.version} "
                f"(vendor — manual install)"
            )
            if event.install_doc_url:
                line += f"\n    [dim]{event.install_doc_url}[/dim]"
            console.print(line)
        elif isinstance(event, ToolSkippedHostUnsupported):
            console.print(
                f"  [yellow]·[/yellow] {event.tool}@{event.version} "
                f"(no pin for host {event.host})"
            )
        elif isinstance(event, ToolFailed):
            console.print(
                f"  [red]✗[/red] {event.tool}@{event.version} "
                f"failed: {event.message} [dim]({event.error_type})[/dim]"
            )

    return _on


__all__ = [
    "human_bytes",
    "make_event_logger",
    "render_install_plan",
    "render_install_summary",
]
