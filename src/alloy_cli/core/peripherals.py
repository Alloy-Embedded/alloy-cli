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
        if overrides.get("tx_dma"):
            payload["tx_dma"] = overrides["tx_dma"]
        if overrides.get("rx_dma"):
            payload["rx_dma"] = overrides["rx_dma"]

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

    proposed = PeripheralEntry(kind="i2c", name=args.name, payload=payload)
    diagnostics.extend(_conflicts.detect(config, proposed))

    cpp_before = _emit.peripherals_cpp(config)
    next_config = _replace_peripherals(config, append=proposed)
    diff = _build_diff(config=config, next_config=next_config, cpp_before=cpp_before)
    return AddResult(diff, tuple(diagnostics), proposed)


# ---------------------------------------------------------------------------
# Generic add — for kinds we don't model in v1 yet
# ---------------------------------------------------------------------------


_GENERIC_KINDS: frozenset[str] = frozenset(
    {"timer", "pwm", "adc", "dac", "can", "dma", "rtc", "watchdog", "qspi", "sdmmc", "usb", "eth"}
)


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
    "add_generic",
    "add_gpio",
    "add_i2c",
    "add_spi",
    "add_uart",
]
