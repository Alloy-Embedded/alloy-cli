"""``alloy devices`` — list + detail for the canonical device IR."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from alloy_cli.core import ir as _ir
from alloy_cli.core import search as _search
from alloy_cli.core.errors import DeviceNotFoundError

JSON_SCHEMA_VERSION = "1.0"


def _device_to_dict(d: _search.DeviceSummary) -> dict[str, Any]:
    return {
        "vendor": d.vendor,
        "family": d.family,
        "device": d.device,
        "package": d.package,
        "core": d.core,
        "summary": d.summary,
        "admitted": d.admitted,
        "has_features": list(d.has_features),
    }


def _print_table(console: Console, results: tuple[_search.DeviceSummary, ...]) -> None:
    if not results:
        console.print("[yellow]no matching devices.[/yellow]")
        return
    table = Table(show_lines=False, header_style="bold magenta")
    table.add_column("device")
    table.add_column("vendor")
    table.add_column("family")
    table.add_column("package")
    table.add_column("core")
    table.add_column("admitted", justify="center")
    table.add_column("features")
    for d in results:
        table.add_row(
            d.device,
            d.vendor or "-",
            d.family or "-",
            d.package or "-",
            d.core or "-",
            "✓" if d.admitted else "•",
            ", ".join(d.has_features) or "-",
        )
    console.print(table)


def _print_detail(console: Console, name: str) -> None:
    """Resolve ``name`` to (vendor, family, device) and print identity."""
    matches = _search.search_devices(
        query=name,
        filters=_search.DeviceFilters(admitted="all"),
    )
    exact = next((d for d in matches if d.device.lower() == name.lower()), None)
    if exact is None and matches:
        exact = matches[0]
    if exact is None:
        raise click.ClickException(
            f"No device matching {name!r}.  Try `alloy devices --search {name}`."
        )
    try:
        ir = _ir.load_device(exact.vendor, exact.family, exact.device)
    except DeviceNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(f"[bold cyan]{ir.identity.device}[/bold cyan]")
    console.print(f"  vendor:   {ir.identity.vendor}")
    console.print(f"  family:   {ir.identity.family}")
    console.print(f"  package:  {ir.identity.package}")
    console.print(f"  core:     {ir.identity.core}")
    console.print(f"  admitted: {'yes' if exact.admitted else 'bulk-admitted'}")
    if ir.identity.summary:
        console.print(f"  summary:  {ir.identity.summary}")

    boards = _search.boards_referencing_device(
        ir.identity.vendor, ir.identity.family, ir.identity.device
    )
    if boards:
        console.print("\n[bold]Boards using this device:[/bold]")
        for b in boards:
            console.print(f"  • {b.board_id} (tier {b.tier})")


@click.command("devices", help="List + search the canonical device IR.")
@click.argument("name", required=False)
@click.option("--search", "query", default=None, help="Free-text query.")
@click.option("--vendor", default=None, help="Filter by vendor (e.g. st, nordic).")
@click.option("--family", default=None, help="Filter by family (e.g. stm32g0).")
@click.option(
    "--has",
    "features",
    multiple=True,
    metavar="FEATURE",
    help="Require a feature; repeatable (e.g. --has usb --has ble).",
)
@click.option(
    "--admitted/--all",
    "only_admitted",
    default=True,
    show_default=True,
    help="Restrict to admitted devices (default) or include bulk-admitted.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON for scripting.")
def devices_command(
    name: str | None,
    query: str | None,
    vendor: str | None,
    family: str | None,
    features: tuple[str, ...],
    only_admitted: bool,
    as_json: bool,
) -> None:
    """List device summaries or print one device's identity."""
    console = Console()
    if name is not None:
        if as_json:
            matches = _search.search_devices(
                query=name,
                filters=_search.DeviceFilters(admitted="all"),
            )
            exact = next((d for d in matches if d.device.lower() == name.lower()), None)
            if exact is None:
                raise click.ClickException(f"No device matching {name!r}.")
            json.dump(_device_to_dict(exact), sys.stdout, sort_keys=True)
            sys.stdout.write("\n")
            return
        _print_detail(console, name)
        return

    results = _search.search_devices(
        query=query,
        filters=_search.DeviceFilters(
            vendor=vendor,
            family=family,
            has=tuple(features),
            admitted="admitted" if only_admitted else "all",
        ),
    )

    if as_json:
        payload = {
            "schema_version": JSON_SCHEMA_VERSION,
            "devices": [_device_to_dict(d) for d in results],
        }
        json.dump(payload, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return

    _print_table(console, results)


__all__ = ["JSON_SCHEMA_VERSION", "devices_command"]
