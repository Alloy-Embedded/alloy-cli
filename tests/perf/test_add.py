"""Peripheral-add happy-path benchmarks."""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core import peripherals as _peripherals
from alloy_cli.core.ir import (
    ConnectionCandidateView,
    DeviceIdentity,
    DeviceIR,
    PeripheralView,
    PinView,
)
from alloy_cli.core.peripherals import AddArgs
from alloy_cli.core.project import (
    ChipRef,
    ProjectConfig,
    ProjectMeta,
)
from tests.perf._budgets import effective_budget


def _ir() -> DeviceIR:
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
        ),
        pins=(
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
        ),
        connection_candidates=(
            ConnectionCandidateView(
                pin="PA9", peripheral="USART1", signal="TX", af_number=1
            ),
            ConnectionCandidateView(
                pin="PA10", peripheral="USART1", signal="RX", af_number=1
            ),
        ),
        dma_routes=(),
        clock_nodes=(),
        package=None,
        payload={},
    )


def _config() -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


@pytest.mark.perf
def test_add_uart_preview_under_budget(benchmark, tmp_path: Path) -> None:
    """A typed `add_uart` preview against the in-memory fixture."""
    config = _config()
    ir = _ir()
    args = AddArgs.of(
        "console",
        peripheral="USART1",
        tx="PA9",
        rx="PA10",
        baud=115200,
    )

    def _invoke() -> None:
        result = _peripherals.add_uart(config, ir, args)
        assert not result.has_errors

    benchmark(_invoke)
    assert benchmark.stats["mean"] < effective_budget("alloy add uart"), (
        f"add_uart mean {benchmark.stats['mean']:.3f}s "
        f"exceeded budget {effective_budget('alloy add uart'):.3f}s"
    )
