"""``ToolchainBadge`` — small status pill for arm-gcc / probe-rs / cmake."""

from __future__ import annotations

from typing import ClassVar

from textual.widgets import Static

from alloy_cli.core.toolchain import ToolchainStatus
from alloy_cli.tui.theme import GLYPH_FAIL, GLYPH_OK


class ToolchainBadge(Static):
    """Render a single :class:`ToolchainStatus` as a colour + glyph pill."""

    DEFAULT_CSS: ClassVar[str] = """
    ToolchainBadge {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self, status: ToolchainStatus, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._status = status

    def render(self):  # type: ignore[override]
        s = self._status
        if s.present:
            label = f"{GLYPH_OK} {s.name}"
            if s.version:
                label += f" {s.version}"
        else:
            label = f"{GLYPH_FAIL} {s.name}"
        return label

    def on_mount(self) -> None:
        css = "toolchain-ok" if self._status.present else "toolchain-missing"
        self.add_class(css)


__all__ = ["ToolchainBadge"]
