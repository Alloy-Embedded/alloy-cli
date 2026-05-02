"""Peripheral wiring operations consumed by ``alloy add``.

Every ``add_*`` function takes a :class:`ProjectConfig` (read from
``alloy.toml``) plus an :class:`AddArgs` and returns an :class:`AddResult`.

The functions are pure: they never touch the filesystem.  The CLI in
:mod:`alloy_cli.commands.add` writes the diff iff it carries no
``error`` diagnostics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alloy_cli.core import conflicts as _conflicts
from alloy_cli.core import emit as _emit
from alloy_cli.core import suggestions as _suggest
from alloy_cli.core.diagnostics import Diagnostic, FilePatch, UnifiedDiff
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.ir import DeviceIR, valid_pins_for
from alloy_cli.core.project import (
    PROJECT_FILE,
    PeripheralEntry,
    ProjectConfig,
    emit_peripheral,
    emit_section,
)

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AddResult:
    """What :func:`add_*` produced."""

    diff: UnifiedDiff
    diagnostics: tuple[Diagnostic, ...]
    proposed: PeripheralEntry | None  # None on validation failure pre-construction

    @property
    def has_errors(self) -> bool:
        return any(d.severity == "error" for d in self.diagnostics)


class PeripheralAddError(AlloyCliError):
    error_type = "peripheral-add-error"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_toml(config: ProjectConfig) -> str:
    """Emit alloy.toml content from ``config`` without touching disk.

    Mirrors :func:`project.write` byte-for-byte using the public
    ``emit_section`` / ``emit_peripheral`` helpers.
    """
    lines: list[str] = [
        f'schema_version = "{config.schema_version}"',
        "",
        "[project]",
        f'name = "{config.project.name}"',
    ]
    if config.project.alloy_cli is not None:
        lines.append(f'alloy-cli = "{config.project.alloy_cli}"')
    if config.project.alloy is not None:
        lines.append(f'alloy = "{config.project.alloy}"')
    if config.project.alloy_codegen is not None:
        lines.append(f'alloy-codegen = "{config.project.alloy_codegen}"')
    if config.project.alloy_devices_yml is not None:
        lines.append(f'alloy-devices-yml = "{config.project.alloy_devices_yml}"')
    lines.append("")
    if config.board is not None:
        lines.extend(["[board]", f'id = "{config.board.id}"', ""])
    if config.chip is not None:
        lines.extend(
            [
                "[chip]",
                f'vendor = "{config.chip.vendor}"',
                f'family = "{config.chip.family}"',
                f'device = "{config.chip.device}"',
                "",
            ]
        )
    lines.extend(emit_section("clocks", config.clocks))
    for peripheral in config.peripherals:
        lines.extend(emit_peripheral(peripheral))
    lines.extend(emit_section("build", config.build))
    lines.extend(emit_section("flash", config.flash))
    return "\n".join(lines).rstrip() + "\n"


def _replace_peripherals(config: ProjectConfig, *, append: PeripheralEntry) -> ProjectConfig:
    return ProjectConfig(
        schema_version=config.schema_version,
        project=config.project,
        board=config.board,
        chip=config.chip,
        clocks=config.clocks,
        peripherals=(*config.peripherals, append),
        build=config.build,
        flash=config.flash,
        raw=config.raw,
    )


def _build_diff(
    *,
    config: ProjectConfig,
    next_config: ProjectConfig,
    cpp_before: str,
) -> UnifiedDiff:
    cpp_after = _emit.peripherals_cpp(next_config)
    return UnifiedDiff(
        patches=(
            FilePatch(
                path=Path(PROJECT_FILE),
                before=_emit_toml(config),
                after=_emit_toml(next_config),
            ),
            FilePatch(
                path=Path("src/peripherals.cpp"),
                before=cpp_before,
                after=cpp_after,
            ),
        )
    )


def _validate_pin(
    ir: DeviceIR,
    *,
    peripheral: str,
    signal: str,
    requested_pin: str,
    field: str,
) -> Diagnostic | None:
    valid = valid_pins_for(ir, peripheral=peripheral, signal=signal)
    if not valid:
        return Diagnostic(
            severity="error",
            code="signal-unknown",
            message=(
                f"Device IR has no candidates for {peripheral}.{signal}; "
                "check the peripheral / signal name."
            ),
            path=field,
        )
    if requested_pin not in valid:
        return Diagnostic(
            severity="error",
            code="invalid-pin",
            message=(
                f"Pin {requested_pin} is not a legal {peripheral}.{signal} mapping for this device."
            ),
            path=field,
            suggestions=tuple(valid[:6]),
        )
    return None


# ---------------------------------------------------------------------------
# AddArgs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AddArgs:
    """Loose carrier for kwargs flowing in from the CLI / TUI / MCP."""

    name: str
    overrides: Mapping[str, Any]

    @classmethod
    def of(cls, name: str, **overrides: Any) -> AddArgs:
        return cls(name=name, overrides=dict(overrides))


# ---------------------------------------------------------------------------
# add_uart
# ---------------------------------------------------------------------------


def add_uart(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="uart", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free UART/USART peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    avoid = set(_conflicts.existing_pin_claims(config.peripherals).keys())
    pin_set = (
        {"TX": overrides.get("tx"), "RX": overrides.get("rx")}
        if overrides.get("tx") and overrides.get("rx")
        else _suggest.suggest_pin_set(
            ir,
            peripheral=instance,
            signals=("TX", "RX"),
            avoid_pins=avoid,
        )
    )
    if pin_set is None or not pin_set.get("TX") or not pin_set.get("RX"):
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-pin-candidates",
                message=f"No free TX/RX pins for {instance}.  Pass --tx / --rx explicitly.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    tx_pin = str(pin_set["TX"])
    rx_pin = str(pin_set["RX"])
    if overrides.get("tx"):
        diag = _validate_pin(
            ir,
            peripheral=instance,
            signal="TX",
            requested_pin=tx_pin,
            field=f"peripherals[{args.name}].tx",
        )
        if diag is not None:
            diagnostics.append(diag)
    if overrides.get("rx"):
        diag = _validate_pin(
            ir,
            peripheral=instance,
            signal="RX",
            requested_pin=rx_pin,
            field=f"peripherals[{args.name}].rx",
        )
        if diag is not None:
            diagnostics.append(diag)

    payload: dict[str, Any] = {
        "kind": "uart",
        "name": args.name,
        "peripheral": instance,
        "tx": tx_pin,
        "rx": rx_pin,
        "baud": int(overrides.get("baud", 115200)),
    }
    for key in ("data_bits", "stop_bits", "parity"):
        value = overrides.get(key)
        if value is not None:
            payload[key] = value
    if overrides.get("dma"):
        payload["dma"] = True
        tx_dma_override = overrides.get("tx_dma")
        rx_dma_override = overrides.get("rx_dma")
        if tx_dma_override or rx_dma_override:
            if tx_dma_override:
                payload["tx_dma"] = tx_dma_override
            if rx_dma_override:
                payload["rx_dma"] = rx_dma_override
        else:
            pair = _suggest.suggest_dma_pair(ir, peripheral=instance, existing=config.peripherals)
            if pair.tx is None and pair.rx is None:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="no-dma-channels",
                        message=(
                            f"No free DMA channels for {instance}.  "
                            "Pass --tx-dma / --rx-dma explicitly or drop --dma."
                        ),
                    )
                )
            if pair.tx is not None:
                payload["tx_dma"] = pair.tx
            if pair.rx is not None:
                payload["rx_dma"] = pair.rx

    proposed = PeripheralEntry(kind="uart", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_gpio
# ---------------------------------------------------------------------------


def add_gpio(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    pin = overrides.get("pin")
    if not pin:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="missing-pin",
                message="GPIO requires --pin.",
                path=f"peripherals[{args.name}].pin",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    # Validate against the IR's pin list (any role) — ignore IR-less devices.
    if ir.pins:
        names = {p.name for p in ir.pins}
        if pin not in names:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="unknown-pin",
                    message=f"Pin {pin} is not in the device IR's pin list.",
                    path=f"peripherals[{args.name}].pin",
                    suggestions=tuple(sorted(names)[:6]),
                )
            )

    payload: dict[str, Any] = {
        "kind": "gpio",
        "name": args.name,
        "pin": pin,
        "mode": str(overrides.get("mode", "output")),
    }
    for key in ("pull", "speed", "label"):
        value = overrides.get(key)
        if value is not None:
            payload[key] = value
    if "initial" in overrides:
        payload["initial"] = int(overrides["initial"])

    proposed = PeripheralEntry(kind="gpio", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_spi
# ---------------------------------------------------------------------------


def add_spi(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="spi", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free SPI peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    signals: tuple[str, ...] = ("SCK", "MISO", "MOSI")
    explicit_pins = {
        "SCK": overrides.get("sck"),
        "MISO": overrides.get("miso"),
        "MOSI": overrides.get("mosi"),
    }
    if all(explicit_pins.values()):
        pin_set = {k: str(v) for k, v in explicit_pins.items()}
    else:
        avoid = set(_conflicts.existing_pin_claims(config.peripherals).keys())
        pin_set = _suggest.suggest_pin_set(
            ir, peripheral=instance, signals=signals, avoid_pins=avoid
        )
        if pin_set is None:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="no-pin-candidates",
                    message=f"No free SCK/MISO/MOSI pin set for {instance}.",
                )
            )
            return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    for signal, requested_pin in pin_set.items():
        if explicit_pins.get(signal):
            diag = _validate_pin(
                ir,
                peripheral=instance,
                signal=signal,
                requested_pin=requested_pin,
                field=f"peripherals[{args.name}].{signal.lower()}",
            )
            if diag is not None:
                diagnostics.append(diag)

    payload: dict[str, Any] = {
        "kind": "spi",
        "name": args.name,
        "peripheral": instance,
        "sck": pin_set["SCK"],
        "miso": pin_set["MISO"],
        "mosi": pin_set["MOSI"],
    }
    if overrides.get("cs"):
        payload["cs"] = overrides["cs"]
    if overrides.get("cs_software") is not None:
        payload["cs_software"] = bool(overrides["cs_software"])
    if "mode" in overrides:
        payload["mode"] = int(overrides["mode"])
    if "frame" in overrides:
        payload["frame"] = int(overrides["frame"])
    if overrides.get("dma"):
        payload["dma"] = True
        tx_dma_override = overrides.get("tx_dma")
        rx_dma_override = overrides.get("rx_dma")
        if tx_dma_override or rx_dma_override:
            if tx_dma_override:
                payload["tx_dma"] = tx_dma_override
            if rx_dma_override:
                payload["rx_dma"] = rx_dma_override
        else:
            pair = _suggest.suggest_dma_pair(ir, peripheral=instance, existing=config.peripherals)
            if pair.tx is None and pair.rx is None:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="no-dma-channels",
                        message=f"No free DMA channels for {instance}.",
                    )
                )
            if pair.tx is not None:
                payload["tx_dma"] = pair.tx
            if pair.rx is not None:
                payload["rx_dma"] = pair.rx
    if "prescaler" in overrides:
        payload["prescaler"] = int(overrides["prescaler"])

    proposed = PeripheralEntry(kind="spi", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_i2c
# ---------------------------------------------------------------------------


def add_i2c(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="i2c", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free I2C peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    explicit_pins = {"SDA": overrides.get("sda"), "SCL": overrides.get("scl")}
    if all(explicit_pins.values()):
        pin_set = {k: str(v) for k, v in explicit_pins.items()}
    else:
        avoid = set(_conflicts.existing_pin_claims(config.peripherals).keys())
        pin_set = _suggest.suggest_pin_set(
            ir, peripheral=instance, signals=("SDA", "SCL"), avoid_pins=avoid
        )
        if pin_set is None:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="no-pin-candidates",
                    message=f"No free SDA/SCL pin set for {instance}.",
                )
            )
            return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    for signal, requested_pin in pin_set.items():
        if explicit_pins.get(signal):
            diag = _validate_pin(
                ir,
                peripheral=instance,
                signal=signal,
                requested_pin=requested_pin,
                field=f"peripherals[{args.name}].{signal.lower()}",
            )
            if diag is not None:
                diagnostics.append(diag)

    payload: dict[str, Any] = {
        "kind": "i2c",
        "name": args.name,
        "peripheral": instance,
        "sda": pin_set["SDA"],
        "scl": pin_set["SCL"],
    }
    if "speed" in overrides:
        payload["speed"] = overrides["speed"]
    if "addressing" in overrides:
        payload["addressing"] = int(overrides["addressing"])
    if overrides.get("dma"):
        payload["dma"] = True
        tx_dma_override = overrides.get("tx_dma")
        rx_dma_override = overrides.get("rx_dma")
        if tx_dma_override or rx_dma_override:
            if tx_dma_override:
                payload["tx_dma"] = tx_dma_override
            if rx_dma_override:
                payload["rx_dma"] = rx_dma_override
        else:
            pair = _suggest.suggest_dma_pair(ir, peripheral=instance, existing=config.peripherals)
            if pair.tx is None and pair.rx is None:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="no-dma-channels",
                        message=f"No free DMA channels for {instance}.",
                    )
                )
            if pair.tx is not None:
                payload["tx_dma"] = pair.tx
            if pair.rx is not None:
                payload["rx_dma"] = pair.rx

    proposed = PeripheralEntry(kind="i2c", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_timer
# ---------------------------------------------------------------------------


def add_timer(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    """Wire a timer peripheral (period_ns + optional divider/mode/interrupt)."""
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="timer", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free timer peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    period_ns = overrides.get("period_ns")
    if period_ns is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="missing-period",
                message="Timer requires --period-ns.",
                path=f"peripherals[{args.name}].period_ns",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    payload: dict[str, Any] = {
        "kind": "timer",
        "name": args.name,
        "peripheral": instance,
        "period_ns": int(period_ns),
    }
    for key in ("divider", "mode", "interrupt"):
        value = overrides.get(key)
        if value is not None:
            payload[key] = value if key != "divider" else int(value)

    proposed = PeripheralEntry(kind="timer", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_pwm
# ---------------------------------------------------------------------------


def add_pwm(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    """PWM channel — pin validated against the IR's connection candidates."""
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="timer", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free timer peripheral with PWM capability.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    channel = overrides.get("channel")
    if channel is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="missing-channel",
                message="PWM requires --channel.",
                path=f"peripherals[{args.name}].channel",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    pin = overrides.get("pin")
    if not pin:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="missing-pin",
                message="PWM requires --pin.",
                path=f"peripherals[{args.name}].pin",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    signal = f"CH{channel}"
    diag = _validate_pin(
        ir,
        peripheral=instance,
        signal=signal,
        requested_pin=pin,
        field=f"peripherals[{args.name}].pin",
    )
    if diag is not None:
        diagnostics.append(diag)

    payload: dict[str, Any] = {
        "kind": "pwm",
        "name": args.name,
        "peripheral": instance,
        "channel": int(channel),
        "pin": pin,
    }
    if "frequency_hz" in overrides:
        payload["frequency_hz"] = int(overrides["frequency_hz"])
    if "duty_cycle" in overrides:
        payload["duty_cycle"] = float(overrides["duty_cycle"])
    if overrides.get("polarity"):
        payload["polarity"] = overrides["polarity"]

    proposed = PeripheralEntry(kind="pwm", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_adc
# ---------------------------------------------------------------------------


def add_adc(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    """ADC with one or more channels.  Channel pins validated per-entry."""
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="adc", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free ADC peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    channels = overrides.get("channels") or ()
    if not channels:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="missing-channels",
                message="ADC requires at least one channel via --channel.",
                path=f"peripherals[{args.name}].channels",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    normalised: list[dict[str, Any]] = []
    for entry in channels:
        if not isinstance(entry, dict):
            continue
        ch = entry.get("channel")
        pin = entry.get("pin")
        if ch is None or not pin:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="invalid-channel",
                    message="Each ADC channel requires --channel <n>:<pin>.",
                )
            )
            continue
        diag = _validate_pin(
            ir,
            peripheral=instance,
            signal=f"IN{ch}",
            requested_pin=str(pin),
            field=f"peripherals[{args.name}].channels[{ch}].pin",
        )
        if diag is not None:
            diagnostics.append(diag)
        normalised.append({"channel": int(ch), "pin": str(pin)})

    payload: dict[str, Any] = {
        "kind": "adc",
        "name": args.name,
        "peripheral": instance,
        "channels": normalised,
    }
    if "resolution" in overrides:
        payload["resolution"] = int(overrides["resolution"])
    if "sample_time_cycles" in overrides:
        payload["sample_time_cycles"] = int(overrides["sample_time_cycles"])
    if overrides.get("dma"):
        payload["dma"] = True

    proposed = PeripheralEntry(kind="adc", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_dac
# ---------------------------------------------------------------------------


def add_dac(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="dac", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free DAC peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    channel = overrides.get("channel")
    pin = overrides.get("pin")
    if channel is None or not pin:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="missing-fields",
                message="DAC requires --channel and --pin.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    diag = _validate_pin(
        ir,
        peripheral=instance,
        signal=f"OUT{channel}",
        requested_pin=str(pin),
        field=f"peripherals[{args.name}].pin",
    )
    if diag is not None:
        diagnostics.append(diag)

    payload: dict[str, Any] = {
        "kind": "dac",
        "name": args.name,
        "peripheral": instance,
        "channel": int(channel),
        "pin": str(pin),
    }
    if overrides.get("output_buffer") is not None:
        payload["output_buffer"] = bool(overrides["output_buffer"])
    if overrides.get("trigger"):
        payload["trigger"] = overrides["trigger"]

    proposed = PeripheralEntry(kind="dac", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_can
# ---------------------------------------------------------------------------


def add_can(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="can", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free CAN peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    avoid = set(_conflicts.existing_pin_claims(config.peripherals).keys())
    explicit = {"TX": overrides.get("tx"), "RX": overrides.get("rx")}
    if all(explicit.values()):
        pin_set = {k: str(v) for k, v in explicit.items()}
    else:
        pin_set = _suggest.suggest_pin_set(
            ir, peripheral=instance, signals=("TX", "RX"), avoid_pins=avoid
        )
        if pin_set is None:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="no-pin-candidates",
                    message=f"No free TX/RX pin set for {instance}.",
                )
            )
            return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    for signal, requested_pin in pin_set.items():
        if explicit.get(signal):
            diag = _validate_pin(
                ir,
                peripheral=instance,
                signal=signal,
                requested_pin=requested_pin,
                field=f"peripherals[{args.name}].{signal.lower()}",
            )
            if diag is not None:
                diagnostics.append(diag)

    payload: dict[str, Any] = {
        "kind": "can",
        "name": args.name,
        "peripheral": instance,
        "tx": pin_set["TX"],
        "rx": pin_set["RX"],
    }
    if "bitrate" in overrides:
        payload["bitrate"] = int(overrides["bitrate"])
    if "sample_point" in overrides:
        payload["sample_point"] = float(overrides["sample_point"])
    if overrides.get("fd") is not None:
        payload["fd"] = bool(overrides["fd"])

    proposed = PeripheralEntry(kind="can", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_usb
# ---------------------------------------------------------------------------


def add_usb(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    mode = overrides.get("mode")
    if mode not in {"device", "host", "otg"}:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="invalid-mode",
                message="USB mode must be one of: device, host, otg.",
                path=f"peripherals[{args.name}].mode",
                suggestions=("device", "host", "otg"),
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="usb", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free USB peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    payload: dict[str, Any] = {
        "kind": "usb",
        "name": args.name,
        "peripheral": instance,
        "mode": mode,
    }
    if overrides.get("vbus_sense") is not None:
        payload["vbus_sense"] = bool(overrides["vbus_sense"])
    if overrides.get("speed"):
        payload["speed"] = overrides["speed"]

    proposed = PeripheralEntry(kind="usb", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# add_eth
# ---------------------------------------------------------------------------


def add_eth(config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
    diagnostics: list[Diagnostic] = []
    overrides = args.overrides

    interface = overrides.get("interface")
    if interface not in {"mii", "rmii"}:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="invalid-interface",
                message="Ethernet interface must be one of: mii, rmii.",
                path=f"peripherals[{args.name}].interface",
                suggestions=("mii", "rmii"),
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    instance = overrides.get("peripheral") or _suggest.suggest_peripheral(
        ir, ip_class="eth", existing=config.peripherals
    )
    if instance is None:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="no-free-instance",
                message="No free Ethernet peripheral on this device.",
            )
        )
        return AddResult(UnifiedDiff(patches=()), tuple(diagnostics), None)

    payload: dict[str, Any] = {
        "kind": "eth",
        "name": args.name,
        "peripheral": instance,
        "interface": interface,
    }
    for key in ("phy_address", "mdc", "mdio"):
        value = overrides.get(key)
        if value is not None:
            payload[key] = int(value) if key == "phy_address" else value
    for key in ("tx_pins", "rx_pins"):
        value = overrides.get(key)
        if value is not None:
            payload[key] = list(value)

    proposed = PeripheralEntry(kind="eth", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# Generic add — for kinds we don't model in v1 yet
# ---------------------------------------------------------------------------


# Kinds whose detailed sub-schema isn't modelled yet — they round-trip
# through ``add_generic`` with an open payload.  Typed wrappers for the
# remaining kinds (rtc / watchdog / qspi / sdmmc / dma) land later.
_GENERIC_KINDS: frozenset[str] = frozenset({"dma", "rtc", "watchdog", "qspi", "sdmmc"})


def add_generic(
    config: ProjectConfig,
    ir: DeviceIR,
    kind: str,
    args: AddArgs,
) -> AddResult:
    """Lightweight add for kinds whose detailed sub-schema isn't modelled in v1.

    The schema treats them as ``kind`` + ``name`` + arbitrary extras;
    we pass the overrides through after a name + conflict check.  When
    later proposals add ``[[peripherals]] timer/pwm/...`` sub-schemas,
    this falls back to a typed ``add_<kind>`` automatically.
    """
    if kind not in _GENERIC_KINDS:
        raise PeripheralAddError(f"Unknown peripheral kind {kind!r}.")
    payload: dict[str, Any] = {"kind": kind, "name": args.name, **dict(args.overrides)}
    proposed = PeripheralEntry(kind=kind, name=args.name, payload=payload)
    diagnostics: list[Diagnostic] = list(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    if not ir.peripherals:
        diagnostics.append(
            Diagnostic(
                severity="info",
                code="no-ir-validation",
                message=(
                    f"Generic add for kind={kind!r} did not run IR validation; "
                    "tighten the schema in a future proposal."
                ),
            )
        )
    return AddResult(diff, tuple(diagnostics), proposed)


__all__ = [
    "AddArgs",
    "AddResult",
    "PeripheralAddError",
    "add_adc",
    "add_can",
    "add_dac",
    "add_eth",
    "add_generic",
    "add_gpio",
    "add_i2c",
    "add_pwm",
    "add_spi",
    "add_timer",
    "add_uart",
    "add_usb",
]
