"""``alloy add <kind>`` — IR-validated peripheral wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console

from alloy_cli.core import ir as _ir
from alloy_cli.core import peripherals as _peripherals
from alloy_cli.core.diagnostics import UnifiedDiff
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.peripherals import AddArgs, AddResult
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig, read


def _load_context(project_dir: Path) -> tuple[ProjectConfig, _ir.DeviceIR]:
    config = read(project_dir / PROJECT_FILE)
    if config.chip is not None:
        device = _ir.load_device(config.chip.vendor, config.chip.family, config.chip.device)
        return config, device
    if config.board is not None:
        from alloy_cli.core import boards as _boards

        try:
            manifest = _boards.lookup(config.board.id)
        except AlloyCliError as exc:
            raise click.ClickException(str(exc)) from exc
        device = _ir.load_device(manifest.vendor, manifest.family, manifest.device)
        return config, device
    raise click.ClickException(
        "alloy.toml has neither [board] nor [chip]; cannot resolve device IR."
    )


def _print_diagnostics(console: Console, result: AddResult) -> None:
    if not result.diagnostics:
        return
    icon = {"error": "[red]✗[/red]", "warning": "[yellow]![/yellow]", "info": "[blue]i[/blue]"}
    for diag in result.diagnostics:
        head = f"{icon.get(diag.severity, '?')} {diag.code}: {diag.message}"
        if diag.path:
            head += f" [dim]({diag.path})[/dim]"
        console.print(head)
        if diag.suggestions:
            preview = ", ".join(diag.suggestions[:6])
            console.print(f"     [dim]suggestions:[/dim] {preview}")


def _apply_diff(project_dir: Path, diff: UnifiedDiff) -> None:
    for patch in diff.patches:
        if not patch.changed:
            continue
        target = project_dir / patch.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch.after, encoding="utf-8")


def _common_options(f):  # type: ignore[no-untyped-def]
    f = click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        default=False,
        help="Write the diff (default: --diff-only).",
    )(f)
    f = click.option(
        "--diff-only",
        is_flag=True,
        default=False,
        help="Print the diff and exit.  Default when --apply is omitted.",
    )(f)
    f = click.option(
        "--project-dir",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        default=Path("."),
        show_default=True,
    )(f)
    return f


def _execute(
    *,
    project_dir: Path,
    do_apply: bool,
    result: AddResult,
) -> None:
    console = Console()
    _print_diagnostics(console, result)

    if result.has_errors:
        raise click.ClickException("Refusing to apply: one or more diagnostics failed.")

    rendered = result.diff.render()
    if not result.diff.changed:
        console.print("[dim]No changes proposed.[/dim]")
        return

    if not do_apply:
        console.print(rendered, highlight=False, markup=False, end="")
        return

    _apply_diff(project_dir, result.diff)
    console.print("[green]✓ Applied[/green] — peripheral added.")


@click.group("add", help="Add a peripheral to the current project.")
def add_command() -> None:
    """``alloy add <kind>``."""


@add_command.command("uart", help="Add a UART/USART peripheral.")
@click.option("--name", required=True, help="Peripheral identifier in alloy.toml.")
@click.option("--peripheral", default=None, help="IP instance, e.g. USART1 (default: lowest free).")
@click.option("--tx", default=None, help="TX pin (default: first IR-valid candidate).")
@click.option("--rx", default=None, help="RX pin (default: first IR-valid candidate).")
@click.option("--baud", type=int, default=115200, show_default=True)
@click.option("--data-bits", "data_bits", type=click.Choice(["7", "8", "9"]), default=None)
@click.option("--stop-bits", "stop_bits", type=click.Choice(["1", "0.5", "1.5", "2"]), default=None)
@click.option("--parity", type=click.Choice(["none", "even", "odd"]), default=None)
@click.option("--dma", is_flag=True, default=False)
@click.option("--tx-dma", "tx_dma", default=None)
@click.option("--rx-dma", "rx_dma", default=None)
@_common_options
def uart(
    name: str,
    peripheral: str | None,
    tx: str | None,
    rx: str | None,
    baud: int,
    data_bits: str | None,
    stop_bits: str | None,
    parity: str | None,
    dma: bool,
    tx_dma: str | None,
    rx_dma: str | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {
        "peripheral": peripheral,
        "tx": tx,
        "rx": rx,
        "baud": baud,
        "data_bits": int(data_bits) if data_bits else None,
        "stop_bits": stop_bits,
        "parity": parity,
        "dma": dma,
        "tx_dma": tx_dma,
        "rx_dma": rx_dma,
    }
    result = _peripherals.add_uart(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("gpio", help="Add a GPIO peripheral.")
@click.option("--name", required=True)
@click.option("--pin", required=True)
@click.option(
    "--mode",
    type=click.Choice(["input", "output", "od", "analog", "alternate"]),
    default="output",
    show_default=True,
)
@click.option("--pull", type=click.Choice(["none", "up", "down"]), default=None)
@click.option("--speed", type=click.Choice(["low", "medium", "high", "very_high"]), default=None)
@click.option("--label", default=None)
@click.option("--initial", type=click.IntRange(0, 1), default=None)
@_common_options
def gpio(
    name: str,
    pin: str,
    mode: str,
    pull: str | None,
    speed: str | None,
    label: str | None,
    initial: int | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"pin": pin, "mode": mode}
    if pull is not None:
        overrides["pull"] = pull
    if speed is not None:
        overrides["speed"] = speed
    if label is not None:
        overrides["label"] = label
    if initial is not None:
        overrides["initial"] = initial
    result = _peripherals.add_gpio(config, device, AddArgs.of(name, **overrides))
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("spi", help="Add an SPI peripheral.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option("--sck", default=None)
@click.option("--miso", default=None)
@click.option("--mosi", default=None)
@click.option("--cs", default=None)
@click.option("--cs-software", "cs_software", is_flag=True, default=False)
@click.option("--mode", type=click.IntRange(0, 3), default=None)
@click.option("--frame", type=click.Choice(["8", "16"]), default=None)
@click.option("--prescaler", type=int, default=None)
@click.option("--dma", is_flag=True, default=False)
@_common_options
def spi(
    name: str,
    peripheral: str | None,
    sck: str | None,
    miso: str | None,
    mosi: str | None,
    cs: str | None,
    cs_software: bool,
    mode: int | None,
    frame: str | None,
    prescaler: int | None,
    dma: bool,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {
        "peripheral": peripheral,
        "sck": sck,
        "miso": miso,
        "mosi": mosi,
        "cs": cs,
        "cs_software": cs_software,
        "mode": mode,
        "frame": int(frame) if frame else None,
        "prescaler": prescaler,
        "dma": dma,
    }
    result = _peripherals.add_spi(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("i2c", help="Add an I2C peripheral.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option("--sda", default=None)
@click.option("--scl", default=None)
@click.option("--speed", type=click.Choice(["standard", "fast", "fast-plus"]), default=None)
@click.option("--addressing", type=click.Choice(["7", "10"]), default=None)
@click.option("--dma", is_flag=True, default=False)
@_common_options
def i2c(
    name: str,
    peripheral: str | None,
    sda: str | None,
    scl: str | None,
    speed: str | None,
    addressing: str | None,
    dma: bool,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {
        "peripheral": peripheral,
        "sda": sda,
        "scl": scl,
        "speed": speed,
        "addressing": int(addressing) if addressing else None,
        "dma": dma,
    }
    result = _peripherals.add_i2c(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


__all__ = ["add_command"]
