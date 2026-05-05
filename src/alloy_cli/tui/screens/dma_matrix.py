"""``DmaMatrixScreen`` — peripheral-by-channel grid with bind / unbind.

The registry factory (:func:`make_dma_matrix`) walks up from the current
working directory to find ``alloy.toml``, resolves the device IR, and
builds a :class:`DmaMatrix` from the IR's ``dma_routes``.  Falls back to
a placeholder when no project or device IR is found.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.dma_matrix import DmaMatrix, DmaMatrixCell, DmaMatrixWidget


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
    DEFAULT_CSS: ClassVar[str] = """
    _DmaMatrixPlaceholder {
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "DMA matrix requires a project with a resolved [chip] or [board].\n"
            "Open a project directory that contains [bold]alloy.toml[/bold] and try again."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matrix_from_ir(ir: object) -> DmaMatrix:
    """Build a :class:`DmaMatrix` from the ``dma_routes`` in *ir*.

    Each :class:`~alloy_cli.core.ir.DmaRouteView` contributes one *free*
    cell in the matrix — the peripheral signal on the row axis and the DMA
    controller on the column axis.  Cells without a matching route are
    implicitly *incompatible* (the widget fills them in as GLYPH_INCOMPATIBLE).
    """
    from alloy_cli.core.ir import DeviceIR

    dev: DeviceIR = ir  # type: ignore[assignment]
    cells: list[DmaMatrixCell] = []
    for route in dev.dma_routes:
        direction = route.direction.lower() if route.direction else ""
        if direction in ("common", ""):
            peripheral_signal = route.peripheral
        else:
            peripheral_signal = f"{route.peripheral}/{route.direction.upper()}"
        cells.append(
            DmaMatrixCell(
                peripheral_signal=peripheral_signal,
                channel=route.controller,
                state="free",
            )
        )
    if not cells:
        return DmaMatrix()
    return DmaMatrix.from_pairs(cells)


def _load_dma_context(project_dir: Path) -> DmaMatrix | None:
    """Return a :class:`DmaMatrix` for the project in *project_dir*, or ``None``."""
    from alloy_cli.core.errors import AlloyCliError
    from alloy_cli.core.project import PROJECT_FILE, read as _read

    toml = project_dir / PROJECT_FILE
    if not toml.exists():
        return None
    try:
        config = _read(toml)
    except AlloyCliError:
        return None

    from alloy_cli.tui.screens.peripheral_add import _resolve_device_for

    device = _resolve_device_for(config)  # type: ignore[arg-type]
    if device is None:
        return None
    return _matrix_from_ir(device)


# ---------------------------------------------------------------------------
# Registry factory
# ---------------------------------------------------------------------------


@register_screen("dma-matrix", title="DMA matrix", description="DMA channel bindings")
def make_dma_matrix() -> Screen:
    """Build a live DmaMatrixScreen from the project in CWD.

    Walks up from the current working directory to find ``alloy.toml``,
    resolves the device IR, and returns a fully-wired matrix screen.
    Returns a placeholder when no project or device IR is found.
    """
    cwd = Path(os.getcwd()).resolve()
    for parent in [cwd, *cwd.parents]:
        matrix = _load_dma_context(parent)
        if matrix is not None:
            return DmaMatrixScreen(matrix=matrix)
    return _DmaMatrixPlaceholder()


__all__ = ["DmaMatrixScreen", "make_dma_matrix"]
