"""``DmaMatrixScreen`` — peripheral-by-channel grid with bind / unbind."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.dma_matrix import DmaMatrix, DmaMatrixWidget


class DmaMatrixScreen(Screen[None]):
    """Render a project's DMA bindings as a peripheral-by-channel grid."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Close")]

    DEFAULT_CSS: ClassVar[str] = """
    DmaMatrixScreen #dma-root {
        padding: 0 1;
    }
    """

    def __init__(self, *, matrix: DmaMatrix) -> None:
        super().__init__()
        self._matrix = matrix

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="dma-root"):
            yield Static("[bold]DMA matrix[/bold]")
            yield DmaMatrixWidget(self._matrix, id="dma-widget")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)


class _DmaMatrixPlaceholder(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("DMA matrix requires a project context.")


@register_screen("dma-matrix", title="DMA matrix", description="DMA channel bindings")
def make_dma_matrix() -> Screen:
    return _DmaMatrixPlaceholder()


__all__ = ["DmaMatrixScreen", "make_dma_matrix"]
