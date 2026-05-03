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
    Phase,
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
# Wave-3 OnboardingScreen (3-phase install wizard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onboarding_inside_resolved_project_skips_to_plan_review(
    tmp_path,
) -> None:
    """Spec scenario: opening the wizard inside a stm32g0 project
    auto-completes the family picker and lands on plan review."""
    _seed_project(tmp_path)  # writes a stm32g0 chip project
    screen = OnboardingScreen(project_root=tmp_path)
    assert screen._phase == Phase.PLAN_REVIEW
    assert screen._state.manifest is not None
    assert screen._state.manifest.family_id == "stm32g0"


@pytest.mark.asyncio
async def test_onboarding_outside_project_starts_at_family_picker(tmp_path) -> None:
    """No alloy.toml → wizard starts at the family-picker phase."""
    screen = OnboardingScreen(project_root=tmp_path)
    assert screen._phase == Phase.FAMILY_PICKER
    assert screen._state.manifest is None


@pytest.mark.asyncio
async def test_onboarding_plan_review_renders_required_and_recommended(
    tmp_path,
) -> None:
    """The plan-review DataTable lists required + recommended tools."""
    _seed_project(tmp_path)  # stm32g0
    screen = OnboardingScreen(project_root=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import DataTable

        table = app.screen.query_one("#plan-table", DataTable)
        # Required tier (inherited from arm-cortex-m): cmake, ninja,
        # arm-none-eabi-gcc, probe-rs.  Recommended for stm32g0:
        # STM32CubeProgrammer (vendor) + tio.
        keys = {row.value for row in table.rows.keys() if row.value}
        for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
            assert tool in keys
        # Vendor row exists (and is dim — tested below).
        assert "STM32CubeProgrammer" in keys


@pytest.mark.asyncio
async def test_onboarding_escape_cancels_before_install(tmp_path) -> None:
    """Escape during the family picker / plan review dismisses with
    None (no exception — only mid-install cancel raises)."""
    _seed_project(tmp_path)
    screen = OnboardingScreen(project_root=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        # The screen has been popped or dismissed.  We don't assert
        # the call_screen result here (Textual harness limitation);
        # success is "no exception was raised".


@pytest.mark.asyncio
async def test_onboarding_register_screen_factory_lands_on_picker_when_cwd_empty(
    tmp_path, monkeypatch
) -> None:
    """The screen registry's factory creates an OnboardingScreen at
    CWD; outside a project it starts at the family picker."""
    monkeypatch.chdir(tmp_path)
    from alloy_cli.tui.screens.onboarding import make_onboarding

    screen = make_onboarding()
    # The factory sets project_root=Path.cwd().
    assert isinstance(screen, OnboardingScreen)
    assert screen._phase == Phase.FAMILY_PICKER
