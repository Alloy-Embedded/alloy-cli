"""Textual-based terminal UI — the Phase-3 differentiator.

This package ships only the foundation in ``add-tui-foundation``:

* :class:`alloy_cli.tui.app.TuiApp` — the Textual app shell.
* :class:`alloy_cli.tui.registry.ScreenRegistry` — discovery for
  the command palette + later proposals.
* Global widgets reused by every Phase-3 screen
  (:class:`CommandPalette`, :class:`DiffModal`, :class:`ValidationPanel`,
  :class:`ToolchainBadge`, :class:`FacetedFilter`).

Per-screen modules (Dashboard, Board Picker, Peripheral Assignment,
Clock Tree, Build Log, …) land in subsequent OpenSpec proposals.
"""

from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.registry import ScreenRegistry, register_screen
from alloy_cli.tui.theme import ColorMode, color_mode

__all__ = [
    "ColorMode",
    "ScreenRegistry",
    "TuiApp",
    "color_mode",
    "register_screen",
]
