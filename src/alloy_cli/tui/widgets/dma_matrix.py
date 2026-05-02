"""``DmaMatrixWidget`` -- peripheral-by-channel grid."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

GLYPH_BOUND = "●"
GLYPH_FREE = "◯"
GLYPH_INCOMPATIBLE = " "
GLYPH_CONFLICT = "✗"


@dataclass(frozen=True, slots=True)
class DmaMatrixCell:
    """One cell in the matrix."""

    peripheral_signal: str
    channel: str
    state: str  # "bound" | "free" | "incompatible" | "conflict"
    holder: str | None = None


@dataclass
class DmaMatrix:
    """Peripheral_signal → channel → cell mapping."""

    rows: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    cells: dict[tuple[str, str], DmaMatrixCell] = field(default_factory=dict)

    @classmethod
    def from_pairs(
        cls,
        cells: Iterable[DmaMatrixCell],
    ) -> DmaMatrix:
        rows: list[str] = []
        columns: list[str] = []
        seen_rows: set[str] = set()
        seen_cols: set[str] = set()
        mapping: dict[tuple[str, str], DmaMatrixCell] = {}
        for cell in cells:
            mapping[(cell.peripheral_signal, cell.channel)] = cell
            if cell.peripheral_signal not in seen_rows:
                rows.append(cell.peripheral_signal)
                seen_rows.add(cell.peripheral_signal)
            if cell.channel not in seen_cols:
                columns.append(cell.channel)
                seen_cols.add(cell.channel)
        return cls(rows=rows, columns=columns, cells=mapping)


def _glyph(state: str) -> str:
    return {
        "bound": GLYPH_BOUND,
        "free": GLYPH_FREE,
        "conflict": GLYPH_CONFLICT,
    }.get(state, GLYPH_INCOMPATIBLE)


class DmaMatrixWidget(Widget):
    """Render a :class:`DmaMatrix` as a text-grid."""

    DEFAULT_CSS: ClassVar[str] = """
    DmaMatrixWidget {
        height: auto;
        padding: 0 1;
    }
    DmaMatrixWidget .matrix-row {
        height: 1;
    }
    """

    def __init__(
        self, matrix: DmaMatrix, *, name: str | None = None, id: str | None = None
    ) -> None:
        super().__init__(name=name, id=id)
        self._matrix = matrix

    @property
    def matrix(self) -> DmaMatrix:
        return self._matrix

    def compose(self) -> ComposeResult:
        with Vertical():
            if not self._matrix.rows:
                yield Static("[dim]No DMA bindings to display.[/dim]")
                return
            header = "                 " + "".join(f" {c:<6}" for c in self._matrix.columns)
            yield Static(header, classes="matrix-row")
            for row in self._matrix.rows:
                cells = [
                    _glyph(
                        self._matrix.cells.get(
                            (row, col), DmaMatrixCell(row, col, "incompatible")
                        ).state
                    )
                    for col in self._matrix.columns
                ]
                line = f"{row:<16} " + "  ".join(f"  {g:^4}" for g in cells)
                yield Static(line, classes="matrix-row")


__all__ = [
    "GLYPH_BOUND",
    "GLYPH_CONFLICT",
    "GLYPH_FREE",
    "DmaMatrix",
    "DmaMatrixCell",
    "DmaMatrixWidget",
]
