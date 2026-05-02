"""``MemoryMapScreen`` — flash + RAM stacked-bar visualisation."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.memory_map import MemoryMap, MemoryMapWidget


class MemoryMapScreen(Screen[None]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Close")]

    DEFAULT_CSS: ClassVar[str] = """
    MemoryMapScreen #memory-root {
        padding: 0 1;
    }
    """

    def __init__(self, *, memory: MemoryMap) -> None:
        super().__init__()
        self._memory = memory

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="memory-root"):
            yield Static("[bold]Memory map[/bold]")
            yield MemoryMapWidget(self._memory, id="memory-widget")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)


class _MemoryMapPlaceholder(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("Memory map requires a build artefact.")


@register_screen("memory-map", title="Memory map", description="Flash + RAM usage")
def make_memory_map() -> Screen:
    return _MemoryMapPlaceholder()


__all__ = ["MemoryMapScreen", "make_memory_map"]
