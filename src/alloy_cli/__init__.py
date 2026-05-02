"""alloy-cli — terminal-native developer surface for the Alloy embedded platform."""

from __future__ import annotations

try:
    from alloy_cli._version import __version__  # type: ignore[import-not-found]
except ImportError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
