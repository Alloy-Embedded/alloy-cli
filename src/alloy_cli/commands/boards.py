"""``alloy boards`` — list + detail for the SDK board catalogue."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from alloy_cli.core import boards as _boards
from alloy_cli.core import search as _search
from alloy_cli.core.errors import BoardNotFoundError

JSON_SCHEMA_VERSION = "1.0"


def _board_to_dict(b: _boards.BoardSummary) -> dict[str, Any]:
    return {
        "board_id": b.board_id,
        "mcu": b.mcu,
        "vendor": b.vendor,
        "family": b.family,
        "device": b.device,
        "core": b.core,
        "flash_size_bytes": b.flash_size_bytes,
        "clock_profiles": list(b.clock_profiles),
        "tier": b.tier,
        "has_features": list(b.has_features),
        "summary": b.summary,
    }


def _print_table(console: Console, results: tuple[_boards.BoardSummary, ...]) -> None:
    if not results:
        console.print("[yellow]no matching boards.[/yellow]")
        return
    table = Table(show_lines=False, header_style="bold magenta")
    table.add_column("board_id")
    table.add_column("mcu")
    table.add_column("vendor")
    table.add_column("family")
    table.add_column("core")
    table.add_column("tier", justify="right")
    table.add_column("features")
    for b in results:
        table.add_row(
            b.board_id,
            b.mcu or "-",
            b.vendor or "-",
            b.family or "-",
            b.core or "-",
            str(b.tier),
            ", ".join(b.has_features) or "-",
        )
    console.print(table)


def _print_detail(console: Console, board_id: str) -> None:
    try:
        manifest = _boards.lookup(board_id)
    except BoardNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[bold cyan]{manifest.board_id}[/bold cyan]")
    console.print(f"  vendor:        {manifest.vendor}")
    console.print(f"  family:        {manifest.family}")
    console.print(f"  device:        {manifest.device}")
    console.print(f"  mcu:           {manifest.mcu}")
    console.print(f"  arch / core:   {manifest.arch}")
    console.print(f"  flash:         {manifest.flash_size_bytes} bytes")
    console.print(f"  tier:          {manifest.summary.tier}")
    profiles = ", ".join(manifest.summary.clock_profiles) or "-"
    console.print(f"  clock_profiles:{profiles}")
    feats = ", ".join(manifest.summary.has_features) or "-"
    console.print(f"  features:      {feats}")
    if manifest.summary.summary:
        console.print(f"  summary:       {manifest.summary.summary}")


@click.command("boards", help="List + search the curated board catalogue.")
@click.argument("board_id", required=False)
@click.option("--search", "query", default=None, help="Free-text query.")
@click.option("--vendor", default=None, help="Filter by vendor (e.g. st, rp).")
@click.option("--isa", default=None, help="Filter by core / ISA (e.g. cortex-m4).")
@click.option(
    "--has",
    "features",
    multiple=True,
    metavar="FEATURE",
    help="Require a feature; repeatable (e.g. --has usb --has ethernet).",
)
@click.option("--tier", type=int, default=None, help="Filter by support tier.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON for scripting.")
def boards_command(
    board_id: str | None,
    query: str | None,
    vendor: str | None,
    isa: str | None,
    features: tuple[str, ...],
    tier: int | None,
    as_json: bool,
) -> None:
    """List boards from the SDK or print one board's manifest."""
    console = Console()

    if board_id is not None:
        if as_json:
            try:
                manifest = _boards.lookup(board_id)
            except BoardNotFoundError as exc:
                raise click.ClickException(str(exc)) from exc
            json.dump(_board_to_dict(manifest.summary), sys.stdout, sort_keys=True)
            sys.stdout.write("\n")
            return
        _print_detail(console, board_id)
        return

    results = _search.search_boards(
        query=query,
        filters=_search.BoardFilters(vendor=vendor, isa=isa, has=tuple(features), tier=tier),
    )

    if as_json:
        payload = {
            "schema_version": JSON_SCHEMA_VERSION,
            "boards": [_board_to_dict(b) for b in results],
        }
        json.dump(payload, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return

    _print_table(console, results)
    if not results and (query or vendor or isa or features or tier is not None):
        console.print(
            "[dim]Tip:[/dim] try `alloy boards --json` to inspect the raw catalogue, or "
            "drop a filter."
        )


__all__ = ["JSON_SCHEMA_VERSION", "boards_command"]
