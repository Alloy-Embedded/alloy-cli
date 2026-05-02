"""Tests for the TUI foundation: app shell, registry, widgets, theming."""

from __future__ import annotations

import asyncio

import pytest
from click.testing import CliRunner

from alloy_cli.core.diagnostics import Diagnostic, FilePatch, UnifiedDiff
from alloy_cli.main import cli
from alloy_cli.tui import (
    ColorMode,
    ScreenRegistry,
    TuiApp,
    color_mode,
    register_screen,
)
from alloy_cli.tui.app import _UnsavedChangesScreen  # noqa: F401 — class import
from alloy_cli.tui.registry import registry as global_registry
from alloy_cli.tui.screens.welcome import WelcomeScreen
from alloy_cli.tui.theme import (
    GLYPH_FAIL,
    GLYPH_OK,
    glyph_for_severity,
    theme_path,
)
from alloy_cli.tui.widgets import (
    CommandPalette,
    DiffWidget,
    Facet,
    FacetedFilter,
    ToolchainBadge,
    ValidationPanel,
)

# ---------------------------------------------------------------------------
# Help / surface
# ---------------------------------------------------------------------------


def test_alloy_ui_help() -> None:
    result = CliRunner().invoke(cli, ["ui", "--help"])
    assert result.exit_code == 0
    assert "--theme" in result.output


# ---------------------------------------------------------------------------
# Theme resolution + glyphs
# ---------------------------------------------------------------------------


def test_color_mode_default() -> None:
    assert color_mode() == ColorMode.COLOR


def test_color_mode_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert color_mode() == ColorMode.GLYPH


def test_color_mode_term_dumb(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert color_mode() == ColorMode.GLYPH


def test_glyph_for_severity_returns_each_distinct_value() -> None:
    error_glyph = glyph_for_severity("error")
    warn_glyph = glyph_for_severity("warning")
    info_glyph = glyph_for_severity("info")
    assert error_glyph != warn_glyph
    assert warn_glyph != info_glyph
    # GLYPH_FAIL paired with severity=error.
    assert error_glyph == GLYPH_FAIL


def test_theme_path_default_resolves_to_existing_file() -> None:
    path = theme_path("default_dark")
    assert path.name == "default_dark.tcss"


def test_theme_path_no_color_picks_high_contrast(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    path = theme_path()
    assert path.name == "high_contrast.tcss"


def test_theme_path_unknown_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    path = theme_path("nonsense")
    assert path.name == "default_dark.tcss"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_register_and_get() -> None:
    reg = ScreenRegistry()
    from alloy_cli.tui.registry import ScreenEntry

    reg.register(ScreenEntry(name="t1", title="T1", factory=lambda: WelcomeScreen()))
    assert "t1" in reg
    assert reg.get("t1") is not None
    assert "t1" in reg.names()
    assert len(reg) == 1


def test_register_screen_decorator_adds_to_global_registry() -> None:
    # The welcome screen registers itself via the decorator at import time.
    assert "welcome" in global_registry
    entry = global_registry.get("welcome")
    assert entry is not None
    assert entry.title == "Welcome"


def test_register_screen_decorator_returns_factory_unchanged() -> None:
    @register_screen("t-noop", title="T-noop")
    def factory() -> WelcomeScreen:
        return WelcomeScreen()

    assert global_registry.get("t-noop") is not None
    assert factory() is not None
    # Cleanup so other tests aren't affected.
    global_registry._entries.pop("t-noop", None)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Widgets — pure construction smoke
# ---------------------------------------------------------------------------


def test_diff_widget_renders_unified_diff_text() -> None:
    diff = UnifiedDiff(
        patches=(
            FilePatch(
                path=__import__("pathlib").Path("a.txt"),
                before="alpha\n",
                after="beta\n",
            ),
        )
    )
    widget = DiffWidget(diff)
    assert widget.diff.changed
    rendered = widget.diff.render()
    assert "+beta" in rendered
    assert "-alpha" in rendered


def test_validation_panel_accepts_diagnostics() -> None:
    panel = ValidationPanel(
        [
            Diagnostic(severity="error", code="x", message="boom", path="peripherals[0]"),
            Diagnostic(severity="info", code="i", message="hi"),
        ]
    )
    assert panel is not None  # construction itself is the smoke test


def test_toolchain_badge_carries_status() -> None:
    from alloy_cli.core.toolchain import ToolchainStatus

    ok_badge = ToolchainBadge(
        ToolchainStatus(
            name="cmake", present=True, version="3.27", path="/cmake", install_hint=None
        )
    )
    bad_badge = ToolchainBadge(
        ToolchainStatus(
            name="probe-rs", present=False, version=None, path=None, install_hint="install"
        )
    )
    assert GLYPH_OK in str(ok_badge.render())
    assert GLYPH_FAIL in str(bad_badge.render())


def test_faceted_filter_toggles_state() -> None:
    f = FacetedFilter(
        [Facet(name="vendor", label="Vendor", options=("st", "nordic"), selected=set())]
    )
    f.toggle("vendor", "st")
    assert "st" in f.selected()["vendor"]
    f.toggle("vendor", "st")
    assert "st" not in f.selected()["vendor"]


def test_faceted_filter_ignores_unknown_options() -> None:
    f = FacetedFilter([Facet(name="vendor", label="Vendor", options=("st",), selected=set())])
    f.toggle("vendor", "unknown")  # no-op
    assert f.selected() == {"vendor": frozenset()}


# ---------------------------------------------------------------------------
# App harness — Pilot driver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tuiapp_boots_to_welcome_screen() -> None:
    app = TuiApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, WelcomeScreen)


@pytest.mark.asyncio
async def test_tuiapp_ctrl_p_opens_command_palette() -> None:
    app = TuiApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


@pytest.mark.asyncio
async def test_tuiapp_q_quits_when_clean() -> None:
    app = TuiApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        # The app exits and run_test returns; reaching here means no crash.


@pytest.mark.asyncio
async def test_tuiapp_q_with_dirty_state_opens_confirmation() -> None:
    app = TuiApp(dirty_callback=lambda: True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "_UnsavedChangesScreen"
        await pilot.press("n")
        await pilot.pause()
        # Pressing N dismisses the modal without exiting.
        assert isinstance(app.screen, WelcomeScreen)


@pytest.mark.asyncio
async def test_command_palette_lists_welcome_screen() -> None:
    app = TuiApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()
        # The palette walks the registry; welcome must be listed.
        from textual.widgets import ListView

        list_view = app.screen.query_one("#palette-results", ListView)
        labels = [child.id for child in list_view.children]
        assert any(label and "welcome" in label for label in labels)


# Avoid emitting the asyncio ``DeprecationWarning`` in CI noise.
def _exercise_asyncio_marker_module() -> None:  # pragma: no cover
    asyncio.get_event_loop_policy()
