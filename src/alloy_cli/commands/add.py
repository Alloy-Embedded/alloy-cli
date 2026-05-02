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


@add_command.command("timer", help="Add a timer peripheral.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option("--period-ns", "period_ns", type=int, required=True)
@click.option("--divider", type=int, default=None)
@click.option("--mode", type=click.Choice(["one_shot", "continuous", "encoder"]), default=None)
@click.option("--interrupt", is_flag=True, default=False)
@_common_options
def timer(
    name: str,
    peripheral: str | None,
    period_ns: int,
    divider: int | None,
    mode: str | None,
    interrupt: bool,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"peripheral": peripheral, "period_ns": period_ns}
    if divider is not None:
        overrides["divider"] = divider
    if mode is not None:
        overrides["mode"] = mode
    if interrupt:
        overrides["interrupt"] = True
    result = _peripherals.add_timer(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("pwm", help="Add a PWM channel.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option("--channel", type=int, required=True)
@click.option("--pin", required=True)
@click.option("--frequency-hz", "frequency_hz", type=int, default=None)
@click.option("--duty-cycle", "duty_cycle", type=float, default=None)
@click.option("--polarity", type=click.Choice(["high", "low"]), default=None)
@_common_options
def pwm(
    name: str,
    peripheral: str | None,
    channel: int,
    pin: str,
    frequency_hz: int | None,
    duty_cycle: float | None,
    polarity: str | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"peripheral": peripheral, "channel": channel, "pin": pin}
    if frequency_hz is not None:
        overrides["frequency_hz"] = frequency_hz
    if duty_cycle is not None:
        overrides["duty_cycle"] = duty_cycle
    if polarity is not None:
        overrides["polarity"] = polarity
    result = _peripherals.add_pwm(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("adc", help="Add an ADC peripheral with one or more channels.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option(
    "--channel",
    "channels",
    multiple=True,
    metavar="N:PIN",
    help="Repeatable; e.g. --channel 0:PA0 --channel 1:PA1.",
)
@click.option("--resolution", type=click.Choice(["8", "10", "12", "14", "16"]), default=None)
@click.option("--sample-time-cycles", "sample_time_cycles", type=int, default=None)
@click.option("--dma", is_flag=True, default=False)
@_common_options
def adc(
    name: str,
    peripheral: str | None,
    channels: tuple[str, ...],
    resolution: str | None,
    sample_time_cycles: int | None,
    dma: bool,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    parsed: list[dict[str, Any]] = []
    for spec in channels:
        if ":" not in spec:
            raise click.BadParameter(f"--channel {spec!r} must be N:PIN.")
        ch, pin = spec.split(":", 1)
        try:
            parsed.append({"channel": int(ch), "pin": pin})
        except ValueError as exc:
            raise click.BadParameter(f"--channel {spec!r} must be N:PIN.") from exc
    overrides: dict[str, Any] = {"peripheral": peripheral, "channels": parsed}
    if resolution is not None:
        overrides["resolution"] = int(resolution)
    if sample_time_cycles is not None:
        overrides["sample_time_cycles"] = sample_time_cycles
    if dma:
        overrides["dma"] = True
    result = _peripherals.add_adc(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("dac", help="Add a DAC channel.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option("--channel", type=int, required=True)
@click.option("--pin", required=True)
@click.option("--output-buffer/--no-output-buffer", "output_buffer", default=None)
@click.option("--trigger", default=None)
@_common_options
def dac(
    name: str,
    peripheral: str | None,
    channel: int,
    pin: str,
    output_buffer: bool | None,
    trigger: str | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"peripheral": peripheral, "channel": channel, "pin": pin}
    if output_buffer is not None:
        overrides["output_buffer"] = output_buffer
    if trigger is not None:
        overrides["trigger"] = trigger
    result = _peripherals.add_dac(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("can", help="Add a CAN bus peripheral.")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option("--tx", default=None)
@click.option("--rx", default=None)
@click.option("--bitrate", type=int, default=None)
@click.option("--sample-point", "sample_point", type=float, default=None)
@click.option("--fd/--no-fd", "fd", default=None)
@_common_options
def can(
    name: str,
    peripheral: str | None,
    tx: str | None,
    rx: str | None,
    bitrate: int | None,
    sample_point: float | None,
    fd: bool | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"peripheral": peripheral, "tx": tx, "rx": rx}
    if bitrate is not None:
        overrides["bitrate"] = bitrate
    if sample_point is not None:
        overrides["sample_point"] = sample_point
    if fd is not None:
        overrides["fd"] = fd
    result = _peripherals.add_can(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("usb", help="Add a USB peripheral (device / host / otg).")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option(
    "--mode",
    type=click.Choice(["device", "host", "otg"], case_sensitive=False),
    required=True,
)
@click.option("--vbus-sense/--no-vbus-sense", "vbus_sense", default=None)
@click.option("--speed", type=click.Choice(["full", "high"]), default=None)
@_common_options
def usb(
    name: str,
    peripheral: str | None,
    mode: str,
    vbus_sense: bool | None,
    speed: str | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"peripheral": peripheral, "mode": mode.lower()}
    if vbus_sense is not None:
        overrides["vbus_sense"] = vbus_sense
    if speed is not None:
        overrides["speed"] = speed
    result = _peripherals.add_usb(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


@add_command.command("eth", help="Add an Ethernet peripheral (MII / RMII).")
@click.option("--name", required=True)
@click.option("--peripheral", default=None)
@click.option(
    "--interface",
    type=click.Choice(["mii", "rmii"], case_sensitive=False),
    required=True,
)
@click.option("--phy-address", "phy_address", type=int, default=None)
@click.option("--mdc", default=None)
@click.option("--mdio", default=None)
@_common_options
def eth(
    name: str,
    peripheral: str | None,
    interface: str,
    phy_address: int | None,
    mdc: str | None,
    mdio: str | None,
    do_apply: bool,
    diff_only: bool,
    project_dir: Path,
) -> None:
    _ = diff_only
    project_dir = project_dir.resolve()
    config, device = _load_context(project_dir)
    overrides: dict[str, Any] = {"peripheral": peripheral, "interface": interface.lower()}
    if phy_address is not None:
        overrides["phy_address"] = phy_address
    if mdc is not None:
        overrides["mdc"] = mdc
    if mdio is not None:
        overrides["mdio"] = mdio
    result = _peripherals.add_eth(
        config, device, AddArgs.of(name, **{k: v for k, v in overrides.items() if v is not None})
    )
    _execute(project_dir=project_dir, do_apply=do_apply, result=result)


__all__ = ["add_command"]
