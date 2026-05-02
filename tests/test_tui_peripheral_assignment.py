"""Tests for the Peripheral Add TUI screen + PinoutWidget."""

from __future__ import annotations

import pytest

from alloy_cli.core.ir import (
    ConnectionCandidateView,
    DeviceIdentity,
    DeviceIR,
    PeripheralView,
    PinView,
)
from alloy_cli.core.project import (
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
)
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.peripheral_add import PeripheralAddScreen
from alloy_cli.tui.widgets import (
    PinoutMode,
    PinoutWidget,
    PinRow,
    PinState,
    rows_from_ir,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
            PeripheralView(name="USART1", ip_name="uart", ip_version=None, base_address=0),
            PeripheralView(name="USART2", ip_name="uart", ip_version=None, base_address=0),
        ),
        pins=(
            PinView(name="PA0", port="A", number=0),
            PinView(name="PA2", port="A", number=2),
            PinView(name="PA3", port="A", number=3),
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
        ),
        connection_candidates=(
            ConnectionCandidateView(pin="PA9", peripheral="USART1", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA10", peripheral="USART1", signal="RX", af_number=1),
            ConnectionCandidateView(pin="PA2", peripheral="USART2", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA3", peripheral="USART2", signal="RX", af_number=1),
        ),
        dma_routes=(),
        clock_nodes=(),
        payload={},
    )


def _empty_config() -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


# ---------------------------------------------------------------------------
# PinoutWidget pure rendering
# ---------------------------------------------------------------------------


def test_rows_from_ir_marks_assigned_and_candidates() -> None:
    rows = rows_from_ir(
        _ir(),
        candidates={"PA9", "PA10"},
        assignments={"PA2": "console"},
    )
    by_name = {r.pin.name: r for r in rows}
    assert by_name["PA2"].state == PinState.ASSIGNED
    assert by_name["PA2"].holder == "console"
    assert by_name["PA9"].state == PinState.CANDIDATE
    assert by_name["PA0"].state == PinState.FREE


def test_pin_row_glyph_per_state() -> None:
    pin = PinView(name="PA1", port="A", number=1)
    row = PinRow(pin=pin, state=PinState.ASSIGNED, holder="led")
    assert row.glyph == "◉"


def test_pinout_widget_falls_back_to_compact_below_threshold() -> None:
    rows = rows_from_ir(_ir())
    widget = PinoutWidget(rows, mode=PinoutMode.SCHEMATIC, terminal_width=80)
    # Schematic mode is rejected when terminal is too narrow.
    assert widget.mode == PinoutMode.COMPACT


def test_pinout_widget_toggle_mode_updates_state() -> None:
    rows = rows_from_ir(_ir())
    widget = PinoutWidget(rows, mode=PinoutMode.COMPACT, terminal_width=140)
    widget.toggle_mode()
    assert widget.mode == PinoutMode.SCHEMATIC
    widget.toggle_mode()
    assert widget.mode == PinoutMode.COMPACT


def test_pinout_widget_toggle_noop_when_terminal_narrow() -> None:
    rows = rows_from_ir(_ir())
    widget = PinoutWidget(rows, mode=PinoutMode.COMPACT, terminal_width=80)
    widget.toggle_mode()
    assert widget.mode == PinoutMode.COMPACT


# ---------------------------------------------------------------------------
# PeripheralAddScreen — Pilot driver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_peripheral_add_screen_initial_status_prompts_for_name(tmp_path) -> None:
    screen = PeripheralAddScreen(
        kind="uart", project_dir=tmp_path, config=_empty_config(), device=_ir()
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Button, Static

        status = app.screen.query_one("#peripheral-status", Static)
        assert "Choose a name" in str(status.render())
        button = app.screen.query_one("#apply-button", Button)
        assert button.disabled is True


@pytest.mark.asyncio
async def test_peripheral_add_screen_validates_with_defaults(tmp_path) -> None:
    screen = PeripheralAddScreen(
        kind="uart", project_dir=tmp_path, config=_empty_config(), device=_ir()
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Button, Input, Static

        name_input = app.screen.query_one("#field-name", Input)
        name_input.value = "console"
        await pilot.pause()
        status = app.screen.query_one("#peripheral-status", Static)
        rendered = str(status.render())
        assert "Will modify" in rendered or "alloy.toml" in rendered
        button = app.screen.query_one("#apply-button", Button)
        assert button.disabled is False


@pytest.mark.asyncio
async def test_peripheral_add_screen_invalid_pin_disables_apply(tmp_path) -> None:
    screen = PeripheralAddScreen(
        kind="uart", project_dir=tmp_path, config=_empty_config(), device=_ir()
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Button, Input

        app.screen.query_one("#field-name", Input).value = "console"
        app.screen.query_one("#field-peripheral", Input).value = "USART1"
        app.screen.query_one("#field-tx", Input).value = "PA12"
        app.screen.query_one("#field-rx", Input).value = "PA13"
        await pilot.pause()
        button = app.screen.query_one("#apply-button", Button)
        assert button.disabled is True


@pytest.mark.asyncio
async def test_peripheral_add_screen_apply_writes_files(tmp_path) -> None:
    screen = PeripheralAddScreen(
        kind="uart", project_dir=tmp_path, config=_empty_config(), device=_ir()
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Input

        app.screen.query_one("#field-name", Input).value = "console"
        await pilot.pause()
        # Trigger apply via the action so we don't depend on focus.
        screen.action_apply()
        await pilot.pause()
        # The screen writes alloy.toml + src/peripherals.cpp under the project_dir.
        assert (tmp_path / "alloy.toml").exists()
        assert (tmp_path / "src" / "peripherals.cpp").exists()


@pytest.mark.asyncio
async def test_peripheral_add_screen_existing_peripheral_in_assignments(tmp_path) -> None:
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(
            PeripheralEntry(
                kind="uart",
                name="debug",
                payload={
                    "kind": "uart",
                    "name": "debug",
                    "peripheral": "USART2",
                    "tx": "PA2",
                    "rx": "PA3",
                },
            ),
        ),
        build={},
        flash={},
        raw={},
    )
    screen = PeripheralAddScreen(kind="uart", project_dir=tmp_path, config=config, device=_ir())
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Input

        app.screen.query_one("#field-name", Input).value = "console2"
        await pilot.pause()
        # Pinout should mark PA2 / PA3 as assigned.
        widget = app.screen.query_one("#peripheral-pinout", PinoutWidget)
        rows = {r.pin.name: r for r in widget.rows}
        assert rows["PA2"].state == PinState.ASSIGNED
        assert rows["PA3"].state == PinState.ASSIGNED


@pytest.mark.asyncio
async def test_peripheral_add_screen_handles_missing_alloy_toml(tmp_path) -> None:
    # No config / device passed in, no alloy.toml on disk.
    screen = PeripheralAddScreen(kind="uart", project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Static

        status = app.screen.query_one("#peripheral-status", Static)
        assert "Cannot read alloy.toml" in str(status.render())
