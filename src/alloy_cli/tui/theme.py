"""Theme + colour-mode resolution for the TUI.

Honours ``NO_COLOR=1`` and ``TERM=dumb`` per the spec, plus an
``ALLOY_TUI_THEME`` env var that picks between the bundled
``default_dark`` / ``high_contrast`` themes.
"""

from __future__ import annotations

import os
from enum import StrEnum
from importlib import resources
from pathlib import Path


class ColorMode(StrEnum):
    """How the TUI should render state cues."""

    COLOR = "color"
    GLYPH = "glyph"  # NO_COLOR / TERM=dumb fallback


def color_mode() -> ColorMode:
    """Resolve the current colour mode from the environment."""
    if os.environ.get("NO_COLOR"):
        return ColorMode.GLYPH
    if os.environ.get("TERM", "").lower() == "dumb":
        return ColorMode.GLYPH
    return ColorMode.COLOR


# Glyph contract (paired with colour for accessibility).
GLYPH_OK = "✓"
GLYPH_FAIL = "✗"
GLYPH_PRESENT = "◉"
GLYPH_ABSENT = "○"
GLYPH_INFO = "◆"
GLYPH_NEXT = "►"


def glyph_for_severity(severity: str) -> str:
    """Map Diagnostic.severity to a glyph (paired with colour in TCSS)."""
    return {"error": GLYPH_FAIL, "warning": GLYPH_INFO, "info": GLYPH_NEXT}.get(severity, " ")


# ---------------------------------------------------------------------------
# Theme files
# ---------------------------------------------------------------------------


_THEME_NAMES = {"default_dark", "high_contrast"}


def theme_path(name: str | None = None) -> Path:
    """Resolve the absolute path to a TCSS theme file.

    Selection order:

    * explicit ``name`` argument (must exist in :data:`_THEME_NAMES`)
    * ``ALLOY_TUI_THEME`` environment variable
    * ``default_dark`` fallback
    """
    requested = name or os.environ.get("ALLOY_TUI_THEME") or "default_dark"
    if requested not in _THEME_NAMES:
        requested = "default_dark"
    if color_mode() is ColorMode.GLYPH:
        # NO_COLOR honour: high_contrast keeps glyphs prominent + drops
        # subtle accent colours.
        requested = "high_contrast"
    return Path(
        str(
            resources.files("alloy_cli")
            .joinpath("tui")
            .joinpath("themes")
            .joinpath(f"{requested}.tcss")
        )
    )


__all__ = [
    "GLYPH_ABSENT",
    "GLYPH_FAIL",
    "GLYPH_INFO",
    "GLYPH_NEXT",
    "GLYPH_OK",
    "GLYPH_PRESENT",
    "ColorMode",
    "color_mode",
    "glyph_for_severity",
    "theme_path",
]
