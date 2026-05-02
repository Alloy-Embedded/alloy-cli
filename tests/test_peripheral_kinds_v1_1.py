"""Tests for the wave-2 typed peripheral kinds + auto-DMA."""

from __future__ import annotations

from typing import Any

import pytest

from alloy_cli.core.ir import (
    ConnectionCandidateView,
    DeviceIdentity,
    DeviceIR,
    DmaRouteView,
    PeripheralView,
    PinView,
)
from alloy_cli.core.peripherals import (
    AddArgs,
    add_adc,
    add_can,
    add_dac,
    add_eth,
    add_pwm,
    add_timer,
    add_uart,
    add_usb,
)
from alloy_cli.core.project import (
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
)
from alloy_cli.core.suggestions import suggest_dma_pair

# ---------------------------------------------------------------------------
# Synthetic IR — covers timer / pwm / adc / dac / can / usb / eth
# ---------------------------------------------------------------------------


def _ir() -> DeviceIR:
    return DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32f4",
            device="stm32f407vg",
            package="lqfp100",
            core="cortex-m4",
            summary="STM32F4",
        ),
        peripherals=(
            PeripheralView(name="USART1", ip_name="uart", ip_version=None, base_address=0),
            PeripheralView(name="USART2", ip_name="uart", ip_version=None, base_address=0),
            PeripheralView(name="SPI1", ip_name="spi", ip_version=None, base_address=0),
            PeripheralView(name="I2C1", ip_name="i2c", ip_version=None, base_address=0),
            PeripheralView(name="TIM2", ip_name="timer", ip_version=None, base_address=0),
            PeripheralView(name="ADC1", ip_name="adc", ip_version=None, base_address=0),
            PeripheralView(name="DAC1", ip_name="dac", ip_version=None, base_address=0),
            PeripheralView(name="CAN1", ip_name="can", ip_version=None, base_address=0),
            PeripheralView(name="USB_OTG_FS", ip_name="usb", ip_version=None, base_address=0),
            PeripheralView(name="ETH", ip_name="eth", ip_version=None, base_address=0),
        ),
        pins=tuple(PinView(name=f"PA{i}", port="A", number=i) for i in range(16))
        + tuple(PinView(name=f"PB{i}", port="B", number=i) for i in range(16)),
        connection_candidates=(
            ConnectionCandidateView(pin="PA9", peripheral="USART1", signal="TX", af_number=7),
            ConnectionCandidateView(pin="PA10", peripheral="USART1", signal="RX", af_number=7),
            ConnectionCandidateView(pin="PA0", peripheral="TIM2", signal="CH1", af_number=1),
            ConnectionCandidateView(pin="PA1", peripheral="TIM2", signal="CH2", af_number=1),
            ConnectionCandidateView(pin="PA0", peripheral="ADC1", signal="IN0", af_number=0),
            ConnectionCandidateView(pin="PA1", peripheral="ADC1", signal="IN1", af_number=0),
            ConnectionCandidateView(pin="PA4", peripheral="DAC1", signal="OUT1", af_number=0),
            ConnectionCandidateView(pin="PA12", peripheral="CAN1", signal="TX", af_number=9),
            ConnectionCandidateView(pin="PA11", peripheral="CAN1", signal="RX", af_number=9),
        ),
        dma_routes=(
            DmaRouteView(
                controller="DMA1",
                peripheral="USART1",
                direction="TX",
                request_value=4,
            ),
            DmaRouteView(
                controller="DMA1",
                peripheral="USART1",
                direction="RX",
                request_value=5,
            ),
            DmaRouteView(
                controller="DMA1",
                peripheral="SPI1",
                direction="TX",
                request_value=3,
            ),
            DmaRouteView(
                controller="DMA1",
                peripheral="SPI1",
                direction="RX",
                request_value=2,
            ),
        ),
        clock_nodes=(),
        payload={},
    )


def _empty_config() -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32f4", device="stm32f407vg"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


def _config_with(*entries: PeripheralEntry) -> ProjectConfig:
    base = _empty_config()
    return ProjectConfig(
        schema_version=base.schema_version,
        project=base.project,
        board=base.board,
        chip=base.chip,
        clocks=base.clocks,
        peripherals=tuple(entries),
        build=base.build,
        flash=base.flash,
        raw=base.raw,
    )


def _peripheral(kind: str, name: str, **payload: Any) -> PeripheralEntry:
    body: dict[str, Any] = {"kind": kind, "name": name, **payload}
    return PeripheralEntry(kind=kind, name=name, payload=body)


# ---------------------------------------------------------------------------
# Auto-DMA on uart / spi / i2c
# ---------------------------------------------------------------------------


def test_uart_dma_picks_tx_and_rx_channels_automatically() -> None:
    config = _empty_config()
    ir = _ir()
    result = add_uart(config, ir, AddArgs.of("console", dma=True))
    assert not result.has_errors
    assert result.proposed is not None
    payload = result.proposed.payload
    assert payload["dma"] is True
    assert payload["tx_dma"] == "DMA1#4"
    assert payload["rx_dma"] == "DMA1#5"


def test_uart_dma_explicit_overrides_win_over_suggestions() -> None:
    config = _empty_config()
    ir = _ir()
    result = add_uart(
        config,
        ir,
        AddArgs.of("console", dma=True, tx_dma="DMA1#9", rx_dma="DMA1#9"),
    )
    assert result.proposed is not None
    assert result.proposed.payload["tx_dma"] == "DMA1#9"
    assert result.proposed.payload["rx_dma"] == "DMA1#9"


def test_uart_dma_no_routes_emits_no_dma_channels_diagnostic() -> None:
    config = _empty_config()
    # Strip dma_routes from the IR copy.
    bare_ir = DeviceIR(
        identity=_ir().identity,
        peripherals=_ir().peripherals,
        pins=_ir().pins,
        connection_candidates=_ir().connection_candidates,
        dma_routes=(),
        clock_nodes=(),
        payload={},
    )
    result = add_uart(config, bare_ir, AddArgs.of("console", dma=True))
    assert result.has_errors
    codes = [d.code for d in result.diagnostics]
    assert "no-dma-channels" in codes


def test_suggest_dma_pair_skips_in_use_channels() -> None:
    ir = _ir()
    existing = (
        _peripheral("uart", "debug", peripheral="USART2", tx="PA2", rx="PA3", tx_dma="DMA1#4"),
    )
    pair = suggest_dma_pair(ir, peripheral="USART1", existing=existing)
    # USART1's only TX route is DMA1#4 — claimed by `debug` — so TX
    # falls through.  RX still resolves to its dedicated DMA1#5.
    assert pair.tx is None
    assert pair.rx == "DMA1#5"


# ---------------------------------------------------------------------------
# add_timer
# ---------------------------------------------------------------------------


def test_add_timer_requires_period_ns() -> None:
    config = _empty_config()
    result = add_timer(config, _ir(), AddArgs.of("loop"))
    assert result.has_errors
    assert any(d.code == "missing-period" for d in result.diagnostics)


def test_add_timer_picks_lowest_free_instance() -> None:
    config = _empty_config()
    result = add_timer(config, _ir(), AddArgs.of("loop", period_ns=1_000_000))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["peripheral"] == "TIM2"
    assert result.proposed.payload["period_ns"] == 1_000_000


# ---------------------------------------------------------------------------
# add_pwm
# ---------------------------------------------------------------------------


def test_add_pwm_validates_pin_against_channel() -> None:
    config = _empty_config()
    result = add_pwm(
        config,
        _ir(),
        AddArgs.of("fan", peripheral="TIM2", channel=1, pin="PA12"),
    )
    assert result.has_errors
    codes = [d.code for d in result.diagnostics]
    assert "invalid-pin" in codes


def test_add_pwm_happy_path_emits_payload() -> None:
    config = _empty_config()
    result = add_pwm(
        config,
        _ir(),
        AddArgs.of(
            "fan",
            peripheral="TIM2",
            channel=1,
            pin="PA0",
            frequency_hz=20_000,
            duty_cycle=0.25,
        ),
    )
    assert not result.has_errors
    assert result.proposed is not None
    payload = result.proposed.payload
    assert payload["channel"] == 1
    assert payload["pin"] == "PA0"
    assert payload["frequency_hz"] == 20_000
    assert payload["duty_cycle"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# add_adc
# ---------------------------------------------------------------------------


def test_add_adc_requires_at_least_one_channel() -> None:
    config = _empty_config()
    result = add_adc(config, _ir(), AddArgs.of("temperature"))
    assert result.has_errors
    assert any(d.code == "missing-channels" for d in result.diagnostics)


def test_add_adc_validates_each_channel_pin() -> None:
    config = _empty_config()
    result = add_adc(
        config,
        _ir(),
        AddArgs.of(
            "temperature",
            peripheral="ADC1",
            channels=[
                {"channel": 0, "pin": "PA0"},
                {"channel": 1, "pin": "PB7"},  # not a valid ADC1.IN1 candidate
            ],
        ),
    )
    assert result.has_errors
    codes = [d.code for d in result.diagnostics]
    assert "invalid-pin" in codes


def test_add_adc_happy_path() -> None:
    config = _empty_config()
    result = add_adc(
        config,
        _ir(),
        AddArgs.of(
            "temperature",
            peripheral="ADC1",
            channels=[{"channel": 0, "pin": "PA0"}, {"channel": 1, "pin": "PA1"}],
            resolution=12,
        ),
    )
    assert not result.has_errors
    assert result.proposed is not None
    assert len(result.proposed.payload["channels"]) == 2
    assert result.proposed.payload["resolution"] == 12


# ---------------------------------------------------------------------------
# add_dac / add_can
# ---------------------------------------------------------------------------


def test_add_dac_validates_pin() -> None:
    config = _empty_config()
    result = add_dac(
        config,
        _ir(),
        AddArgs.of("audio", peripheral="DAC1", channel=1, pin="PB6"),
    )
    assert result.has_errors


def test_add_dac_happy_path() -> None:
    config = _empty_config()
    result = add_dac(
        config,
        _ir(),
        AddArgs.of("audio", peripheral="DAC1", channel=1, pin="PA4"),
    )
    assert not result.has_errors


def test_add_can_default_pins_resolved_from_ir() -> None:
    config = _empty_config()
    result = add_can(config, _ir(), AddArgs.of("powertrain", bitrate=500_000))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["tx"] == "PA12"
    assert result.proposed.payload["rx"] == "PA11"


# ---------------------------------------------------------------------------
# add_usb / add_eth
# ---------------------------------------------------------------------------


def test_add_usb_rejects_invalid_mode() -> None:
    config = _empty_config()
    result = add_usb(config, _ir(), AddArgs.of("dev", mode="peripheral"))
    assert result.has_errors
    codes = [d.code for d in result.diagnostics]
    assert "invalid-mode" in codes


def test_add_usb_happy_path() -> None:
    config = _empty_config()
    result = add_usb(config, _ir(), AddArgs.of("dev", mode="device", speed="full"))
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["mode"] == "device"
    assert result.proposed.payload["speed"] == "full"


def test_add_eth_rejects_invalid_interface() -> None:
    config = _empty_config()
    result = add_eth(config, _ir(), AddArgs.of("net", interface="rgmii"))
    assert result.has_errors
    codes = [d.code for d in result.diagnostics]
    assert "invalid-interface" in codes


def test_add_eth_happy_path() -> None:
    config = _empty_config()
    result = add_eth(
        config,
        _ir(),
        AddArgs.of("net", interface="rmii", phy_address=1, mdc="PC1", mdio="PA2"),
    )
    assert not result.has_errors
    assert result.proposed is not None
    assert result.proposed.payload["interface"] == "rmii"
    assert result.proposed.payload["phy_address"] == 1


# ---------------------------------------------------------------------------
# Schema 1.1 round-trip
# ---------------------------------------------------------------------------


def test_schema_1_0_files_still_parse() -> None:
    from alloy_cli.core.project import parse

    payload = {
        "schema_version": "1.0.0",
        "project": {"name": "demo"},
        "chip": {"vendor": "st", "family": "stm32f4", "device": "stm32f407vg"},
        "peripherals": [
            {
                "kind": "uart",
                "name": "console",
                "peripheral": "USART1",
                "tx": "PA9",
                "rx": "PA10",
            }
        ],
    }
    cfg = parse(payload)
    assert cfg.schema_version == "1.0.0"
    assert len(cfg.peripherals) == 1


def test_schema_1_1_timer_missing_period_ns_fails() -> None:
    from alloy_cli.core.errors import ProjectConfigError
    from alloy_cli.core.project import parse

    payload = {
        "schema_version": "1.1.0",
        "project": {"name": "demo"},
        "chip": {"vendor": "st", "family": "stm32f4", "device": "stm32f407vg"},
        "peripherals": [
            {
                "kind": "timer",
                "name": "loop",
                "peripheral": "TIM2",
                # period_ns missing — should fail
            }
        ],
    }
    with pytest.raises(ProjectConfigError, match="period_ns"):
        parse(payload)


def test_schema_1_1_usb_invalid_mode_fails() -> None:
    from alloy_cli.core.errors import ProjectConfigError
    from alloy_cli.core.project import parse

    payload = {
        "schema_version": "1.1.0",
        "project": {"name": "demo"},
        "chip": {"vendor": "st", "family": "stm32f4", "device": "stm32f407vg"},
        "peripherals": [
            {
                "kind": "usb",
                "name": "dev",
                "peripheral": "USB_OTG_FS",
                "mode": "peripheral",  # not in {device, host, otg}
            }
        ],
    }
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)
