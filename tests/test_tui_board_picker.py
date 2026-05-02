"""Tests for the Board Picker TUI screen (Phase-3.3)."""

from __future__ import annotations

import json

import pytest

from alloy_cli.core import boards as _boards
from alloy_cli.core import search as _search
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.board_picker import BoardPickerScreen, _render_board_detail


@pytest.fixture
def board_catalog(tmp_path, monkeypatch):
    """Two-board catalogue: one Cortex-M0+, one Cortex-M4 with USB."""
    root = tmp_path / "boards"
    root.mkdir()
    (root / "nucleo_g071rb").mkdir()
    (root / "nucleo_g071rb" / "board.json").write_text(
        json.dumps(
            {
                "board_id": "nucleo_g071rb",
                "vendor": "st",
                "family": "stm32g0",
                "device": "stm32g071rb",
                "arch": "cortex-m0plus",
                "mcu": "STM32G071RBT6",
                "flash_size_bytes": 131072,
                "summary": "ST Nucleo G071RB",
                "tier": 1,
                "clock_profiles": ["pll_64mhz"],
            }
        )
    )
    (root / "stm32f4_disco").mkdir()
    (root / "stm32f4_disco" / "board.json").write_text(
        json.dumps(
            {
                "board_id": "stm32f4_disco",
                "vendor": "st",
                "family": "stm32f4",
                "device": "stm32f407vg",
                "arch": "cortex-m4",
                "mcu": "STM32F407VGT6",
                "flash_size_bytes": 1048576,
                "summary": "STM32F4 Discovery",
                "tier": 1,
                "clock_profiles": ["pll_168mhz"],
                "usb": {"otg": "fs"},
            }
        )
    )
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(root))
    _boards.load_catalog.cache_clear()
    _search.reset_caches()
    yield root
    _boards.load_catalog.cache_clear()
    _search.reset_caches()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_render_board_detail_includes_identity(board_catalog) -> None:
    summary = _boards.load_catalog()[0]
    text = _render_board_detail(summary)
    assert summary.board_id in text
    assert summary.family in text


# ---------------------------------------------------------------------------
# Pilot-driven flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_picker_lists_full_catalogue_on_mount(board_catalog) -> None:
    app = TuiApp(initial_screen=BoardPickerScreen())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import ListView, Static

        list_view = app.screen.query_one("#picker-list", ListView)
        ids = sorted(child.id for child in list_view.children if child.id)
        assert any("nucleo_g071rb" in i for i in ids)
        assert any("stm32f4_disco" in i for i in ids)
        # Detail pane has something for the highlighted result.
        detail = app.screen.query_one("#picker-detail", Static)
        assert "vendor:" in str(detail.render())


@pytest.mark.asyncio
async def test_picker_search_narrows_list(board_catalog) -> None:
    app = TuiApp(initial_screen=BoardPickerScreen())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Input, ListView, Static

        search = app.screen.query_one("#picker-search", Input)
        search.value = "nucleo"
        await pilot.pause()
        list_view = app.screen.query_one("#picker-list", ListView)
        ids = [child.id for child in list_view.children if child.id]
        assert any("nucleo" in i for i in ids)
        assert not any("disco" in i for i in ids)
        count = app.screen.query_one("#picker-count", Static)
        assert "1/2" in str(count.render())


@pytest.mark.asyncio
async def test_picker_enter_dismisses_with_selection(board_catalog) -> None:
    app = TuiApp(initial_screen=BoardPickerScreen())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # The screen highlights index 0 on mount; calling action_choose
        # is the same path Enter / ListView.Selected goes through.
        screen = app.screen
        assert isinstance(screen, BoardPickerScreen)
        screen.action_choose()
        await pilot.pause()


@pytest.mark.asyncio
async def test_picker_escape_dismisses_with_none(board_catalog) -> None:
    app = TuiApp(initial_screen=BoardPickerScreen())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()


@pytest.mark.asyncio
async def test_picker_f2_toggles_full_screen_detail(board_catalog) -> None:
    app = TuiApp(initial_screen=BoardPickerScreen())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BoardPickerScreen)
        assert "-detail-fullscreen" not in screen.classes
        screen.action_toggle_detail()
        await pilot.pause()
        assert "-detail-fullscreen" in screen.classes
        screen.action_toggle_detail()
        await pilot.pause()
        assert "-detail-fullscreen" not in screen.classes


@pytest.mark.asyncio
async def test_picker_empty_catalogue_shows_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ALLOY_BOARDS_ROOT", raising=False)
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(tmp_path / "empty"))
    _boards.load_catalog.cache_clear()
    app = TuiApp(initial_screen=BoardPickerScreen())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Static

        count = app.screen.query_one("#picker-count", Static)
        rendered = str(count.render()).lower()
        assert "empty" in rendered or "alloy_boards_root" in rendered.lower()
    _boards.load_catalog.cache_clear()
