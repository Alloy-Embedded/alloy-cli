"""Tests for Dashboard + Onboarding screens (Phase-3.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alloy_cli.core.project import (
    PROJECT_FILE,
    BoardRef,
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.dashboard import (
    DashboardScreen,
    _read_build_summary,
    _render_memory_bar,
)
from alloy_cli.tui.screens.onboarding import (
    OnboardingScreen,
    _OnboardingState,
    load_state,
    persist_state,
    state_path,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_project(
    root: Path,
    *,
    peripherals: tuple[PeripheralEntry, ...] = (),
    chip: bool = True,
) -> None:
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None if chip else BoardRef(id="nucleo_g071rb"),
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb") if chip else None,
        clocks={"profile": "default_pll_64mhz"},
        peripherals=peripherals,
        build={"profile": "debug"},
        flash={},
        raw={},
    )
    write(root / PROJECT_FILE, config)


def _peripheral(kind: str, name: str, **payload) -> PeripheralEntry:
    body = {"kind": kind, "name": name, **payload}
    return PeripheralEntry(kind=kind, name=name, payload=body)


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------


def test_render_memory_bar_zero_capacity_returns_unknown() -> None:
    assert "?" in _render_memory_bar(used=10, total=0, label="FLASH")
    assert "?" in _render_memory_bar(used=None, total=None, label="RAM")


def test_render_memory_bar_full_bar() -> None:
    text = _render_memory_bar(used=1024, total=1024, label="RAM")
    assert "100%" in text
    assert "█" in text


def test_read_build_summary_returns_none_when_absent(tmp_path) -> None:
    from alloy_cli.core.project import AlloyDir

    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    assert _read_build_summary(layout) is None


def test_read_build_summary_parses_payload(tmp_path) -> None:
    from alloy_cli.core.project import AlloyDir

    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    (layout.cache / "last_build.json").write_text(
        json.dumps(
            {
                "profile": "debug",
                "ok": True,
                "elf": "firmware.elf",
                "flash_bytes": 10240,
                "ram_bytes": 1024,
                "flash_capacity": 131072,
                "ram_capacity": 36864,
                "timestamp": "2026-05-01T20:00:00Z",
            }
        )
    )
    summary = _read_build_summary(layout)
    assert summary is not None
    assert summary.ok is True
    assert summary.flash_bytes == 10240
    assert summary.ram_capacity == 36864


# ---------------------------------------------------------------------------
# Onboarding state persistence
# ---------------------------------------------------------------------------


def test_onboarding_state_round_trip(tmp_path) -> None:
    state = _OnboardingState(
        name="firmware",
        board_id="nucleo_g071rb",
        clock_profile="pll_64mhz",
        starter_peripheral_kind="uart",
        skipped={"Starter peripheral"},
    )
    persist_state(tmp_path, state)
    assert state_path(tmp_path).exists()
    decoded = load_state(tmp_path)
    assert decoded is not None
    assert decoded.name == "firmware"
    assert decoded.board_id == "nucleo_g071rb"
    assert decoded.clock_profile == "pll_64mhz"
    assert "Starter peripheral" in decoded.skipped


def test_load_state_returns_none_when_absent(tmp_path) -> None:
    assert load_state(tmp_path) is None


def test_onboarding_state_to_from_dict_handles_device_tuple(tmp_path) -> None:
    state = _OnboardingState(
        name="raw", device=("st", "stm32g0", "stm32g071rb"), license="Apache-2.0"
    )
    persist_state(tmp_path, state)
    decoded = load_state(tmp_path)
    assert decoded is not None
    assert decoded.device == ("st", "stm32g0", "stm32g071rb")
    assert decoded.license == "Apache-2.0"


# ---------------------------------------------------------------------------
# Dashboard composition (Pilot-driven)
# ---------------------------------------------------------------------------


def _texts(widget) -> list[str]:
    """Walk a widget's ``Static`` descendants and dump their rendered text."""
    return [str(s.render()) for s in widget.query("Static")]


@pytest.mark.asyncio
async def test_dashboard_renders_empty_project_message(tmp_path) -> None:
    _seed_project(tmp_path)
    screen = DashboardScreen(project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        peripherals = app.screen.query_one("#dash-peripherals")
        joined = "\n".join(_texts(peripherals))
        assert "No peripherals yet" in joined


@pytest.mark.asyncio
async def test_dashboard_renders_peripherals_for_configured_project(tmp_path) -> None:
    _seed_project(
        tmp_path,
        peripherals=(
            _peripheral("uart", "console", peripheral="USART2", tx="PA2", rx="PA3"),
            _peripheral("gpio", "led", pin="PA5", mode="output"),
        ),
    )
    screen = DashboardScreen(project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        peripherals = app.screen.query_one("#dash-peripherals")
        joined = "\n".join(_texts(peripherals))
        assert "console" in joined
        assert "led" in joined


@pytest.mark.asyncio
async def test_dashboard_renders_build_summary_when_present(tmp_path) -> None:
    _seed_project(tmp_path)
    cache = tmp_path / ".alloy" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "last_build.json").write_text(
        json.dumps(
            {
                "profile": "debug",
                "ok": True,
                "elf": "firmware.elf",
                "flash_bytes": 5120,
                "flash_capacity": 131072,
                "ram_bytes": 512,
                "ram_capacity": 36864,
                "timestamp": "2026-05-01T20:00:00Z",
            }
        )
    )
    screen = DashboardScreen(project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        build_text = "\n".join(_texts(app.screen.query_one("#dash-build")))
        memory_text = "\n".join(_texts(app.screen.query_one("#dash-memory")))
        assert "profile=debug" in build_text
        assert "FLASH" in memory_text
        assert "RAM" in memory_text


@pytest.mark.asyncio
async def test_dashboard_falls_back_when_alloy_toml_unreadable(tmp_path) -> None:
    # Don't write alloy.toml — DashboardScreen should display an error banner.
    screen = DashboardScreen(project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        joined = "\n".join(_texts(app.screen))
        assert "Could not read alloy.toml" in joined


@pytest.mark.asyncio
async def test_dashboard_hotkeys_emit_notifications(tmp_path) -> None:
    _seed_project(tmp_path)
    screen = DashboardScreen(project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("b")  # noop hotkey — must not crash
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()


# ---------------------------------------------------------------------------
# Onboarding wizard (Pilot-driven)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onboarding_advances_through_steps(tmp_path) -> None:
    screen = OnboardingScreen(root=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Step 1: name input.
        from textual.widgets import Input

        name_input = app.screen.query_one("#step-name", Input)
        name_input.value = "firmware"
        # Click "Next".
        from textual.widgets import Button

        next_button = app.screen.query_one("#next", Button)
        await pilot.click(next_button)
        await pilot.pause()
        # Step 2: board input — skip via the Skip button instead.
        skip_button = app.screen.query_one("#skip", Button)
        await pilot.click(skip_button)
        await pilot.pause()
        # State persisted to disk.
        from_disk = load_state(tmp_path)
        assert from_disk is not None
        assert from_disk.name == "firmware"


@pytest.mark.asyncio
async def test_onboarding_save_and_exit_dismisses(tmp_path) -> None:
    screen = OnboardingScreen(root=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        # State file written even before completing all steps.
        assert state_path(tmp_path).exists()


@pytest.mark.asyncio
async def test_onboarding_escape_cancels(tmp_path) -> None:
    screen = OnboardingScreen(root=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
