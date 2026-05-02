"""Tests for ``alloy_cli.core.peripherals`` — the engine behind ``alloy add``."""

from __future__ import annotations

from typing import Any

import pytest

from alloy_cli.core import emit as _emit
from alloy_cli.core.diagnostics import Diagnostic
from alloy_cli.core.ir import (
    ConnectionCandidateView,
    DeviceIdentity,
    DeviceIR,
    PeripheralView,
    PinView,
)
from alloy_cli.core.peripherals import (
    AddArgs,
    add_generic,
    add_gpio,
    add_i2c,
    add_spi,
    add_uart,
)
from alloy_cli.core.project import (
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
)

# ---------------------------------------------------------------------------
# Synthetic IR
# ---------------------------------------------------------------------------


def _make_ir() -> DeviceIR:
    return DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32g0",
            device="stm32g071rb",
            package="lqfp64",
            core="cortex-m0plus",
            summary="STM32G0",
        ),
        peripherals=(
            PeripheralView(
                name="USART1", ip_name="uart", ip_version=None, base_address=0x4001_3800
            ),
            PeripheralView(
                name="USART2", ip_name="uart", ip_version=None, base_address=0x4000_4400
            ),
            PeripheralView(name="SPI1", ip_name="spi", ip_version=None, base_address=0x4001_3000),
            PeripheralView(name="I2C1", ip_name="i2c", ip_version=None, base_address=0x4000_5400),
        ),
        pins=(
            PinView(name="PA2", port="A", number=2),
            PinView(name="PA3", port="A", number=3),
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
            PinView(name="PA5", port="A", number=5),
            PinView(name="PA6", port="A", number=6),
            PinView(name="PA7", port="A", number=7),
            PinView(name="PB6", port="B", number=6),
            PinView(name="PB7", port="B", number=7),
        ),
        connection_candidates=(
            ConnectionCandidateView(pin="PA9", peripheral="USART1", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA10", peripheral="USART1", signal="RX", af_number=1),
            ConnectionCandidateView(pin="PA2", peripheral="USART2", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA3", peripheral="USART2", signal="RX", af_number=1),
            ConnectionCandidateView(pin="PA5", peripheral="SPI1", signal="SCK", af_number=0),
            ConnectionCandidateView(pin="PA6", peripheral="SPI1", signal="MISO", af_number=0),
            ConnectionCandidateView(pin="PA7", peripheral="SPI1", signal="MOSI", af_number=0),
            ConnectionCandidateView(pin="PB7", peripheral="I2C1", signal="SDA", af_number=4),
            ConnectionCandidateView(pin="PB6", peripheral="I2C1", signal="SCL", af_number=4),
        ),
        dma_routes=(),
        clock_nodes=(),
        payload={},
    )


def _empty_config(name: str = "fw") -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name=name),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


def _config_with_peripherals(*entries: PeripheralEntry) -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="fw"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=tuple(entries),
        build={},
        flash={},
        raw={},
    )


def _peripheral(kind: str, name: str, **payload: Any) -> PeripheralEntry:
    body: dict[str, Any] = {"kind": kind, "name": name}
    body.update(payload)
    return PeripheralEntry(kind=kind, name=name, payload=body)


# ---------------------------------------------------------------------------
# add_uart
# ---------------------------------------------------------------------------


def test_add_uart_with_defaults_picks_first_free_instance_and_pins() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_uart(config, ir, AddArgs.of("app"))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["peripheral"] == "USART1"
    assert result.proposed.payload["tx"] == "PA9"
    assert result.proposed.payload["rx"] == "PA10"
    assert result.proposed.payload["baud"] == 115200
    assert result.diff.changed


def test_add_uart_skips_in_use_instance() -> None:
    config = _config_with_peripherals(
        _peripheral("uart", "console", peripheral="USART1", tx="PA9", rx="PA10")
    )
    ir = _make_ir()
    result = add_uart(config, ir, AddArgs.of("app"))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["peripheral"] == "USART2"


def test_add_uart_invalid_pin_emits_diagnostic_with_suggestions() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_uart(config, ir, AddArgs.of("app", peripheral="USART1", tx="PA12", rx="PA13"))
    assert result.has_errors
    assert any("PA12" in d.message for d in result.diagnostics)
    bad = next(d for d in result.diagnostics if d.code == "invalid-pin")
    assert "PA9" in bad.suggestions  # legal alternative listed


def test_add_uart_pin_in_use_raises_conflict_diagnostic() -> None:
    config = _config_with_peripherals(
        _peripheral("uart", "debug", peripheral="USART2", tx="PA2", rx="PA3"),
    )
    ir = _make_ir()
    result = add_uart(config, ir, AddArgs.of("app", peripheral="USART2", tx="PA2", rx="PA3"))
    assert result.has_errors
    codes = [d.code for d in result.diagnostics]
    assert "instance-in-use" in codes
    assert "pin-in-use" in codes


def test_add_uart_passes_baud_data_bits_and_parity() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_uart(
        config,
        ir,
        AddArgs.of("app", baud=921600, data_bits=8, parity="even", stop_bits="1"),
    )
    assert result.proposed is not None
    assert result.proposed.payload["baud"] == 921600
    assert result.proposed.payload["data_bits"] == 8
    assert result.proposed.payload["parity"] == "even"
    assert result.proposed.payload["stop_bits"] == "1"


def test_add_uart_with_dma_threads_options() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_uart(
        config,
        ir,
        AddArgs.of("app", dma=True, tx_dma="DMA1#1", rx_dma="DMA1#2"),
    )
    assert result.proposed is not None
    assert result.proposed.payload["dma"] is True
    assert result.proposed.payload["tx_dma"] == "DMA1#1"
    assert result.proposed.payload["rx_dma"] == "DMA1#2"


# ---------------------------------------------------------------------------
# add_gpio
# ---------------------------------------------------------------------------


def test_add_gpio_requires_pin() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_gpio(config, ir, AddArgs.of("led"))
    assert result.has_errors
    assert any(d.code == "missing-pin" for d in result.diagnostics)


def test_add_gpio_unknown_pin_emits_diagnostic() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_gpio(config, ir, AddArgs.of("led", pin="ZZ99"))
    assert result.has_errors
    assert any(d.code == "unknown-pin" for d in result.diagnostics)


def test_add_gpio_passes_label_and_initial() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_gpio(config, ir, AddArgs.of("led", pin="PA5", label="LD2", initial=1))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["pin"] == "PA5"
    assert result.proposed.payload["label"] == "LD2"
    assert result.proposed.payload["initial"] == 1


def test_add_gpio_pin_in_use_emits_pin_conflict() -> None:
    config = _config_with_peripherals(_peripheral("gpio", "led", pin="PA5", mode="output"))
    ir = _make_ir()
    result = add_gpio(config, ir, AddArgs.of("led2", pin="PA5"))
    assert result.has_errors
    assert any(d.code == "pin-in-use" for d in result.diagnostics)


# ---------------------------------------------------------------------------
# add_spi / add_i2c smoke
# ---------------------------------------------------------------------------


def test_add_spi_picks_default_pins() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_spi(config, ir, AddArgs.of("flash"))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["sck"] == "PA5"
    assert result.proposed.payload["miso"] == "PA6"
    assert result.proposed.payload["mosi"] == "PA7"


def test_add_i2c_picks_default_pins() -> None:
    config = _empty_config()
    ir = _make_ir()
    result = add_i2c(config, ir, AddArgs.of("sensor"))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["sda"] == "PB7"
    assert result.proposed.payload["scl"] == "PB6"


# ---------------------------------------------------------------------------
# Generic kinds
# ---------------------------------------------------------------------------


def test_add_generic_writes_kind_and_name() -> None:
    """Generic add still works for kinds without a typed wrapper (rtc/qspi/...)."""
    config = _empty_config()
    ir = _make_ir()
    result = add_generic(config, ir, "rtc", AddArgs.of("rtc0", source="LSI"))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.kind == "rtc"
    assert result.proposed.payload["source"] == "LSI"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_emit_peripherals_cpp_is_deterministic() -> None:
    config = _config_with_peripherals(
        _peripheral("gpio", "led", pin="PA5", mode="output"),
        _peripheral("uart", "console", peripheral="USART2", tx="PA2", rx="PA3", baud=115200),
    )
    a = _emit.peripherals_cpp(config)
    b = _emit.peripherals_cpp(config)
    assert a == b
    assert "alloy::Gpio led" in a
    assert "alloy::Uart console" in a


def test_re_running_add_produces_no_diff_on_settled_config() -> None:
    config = _config_with_peripherals(_peripheral("gpio", "led", pin="PA5", mode="output"))
    ir = _make_ir()
    result = add_gpio(config, ir, AddArgs.of("led", pin="PA5"))
    # Adding an entry whose name already exists should produce a duplicate
    # diagnostic; the project would not change.
    assert any(d.code == "duplicate-name" for d in result.diagnostics)


# ---------------------------------------------------------------------------
# Diagnostic shape
# ---------------------------------------------------------------------------


def test_diagnostic_severity_set_includes_error() -> None:
    diag = Diagnostic(severity="error", code="x", message="y")
    assert diag.severity == "error"


# Suppress flake8 unused-imports if pytest doesn't surface them
__all__ = ["pytest"]
