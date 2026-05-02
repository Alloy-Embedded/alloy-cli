"""``PinoutWidget`` — pin list with state + candidate highlighting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from alloy_cli.core.ir import DeviceIR, PackageView, PinView
from alloy_cli.tui.widgets.pinout_layout import PinoutCell, pick_layout


class PinState(StrEnum):
    FREE = "free"
    CANDIDATE = "candidate"
    ASSIGNED = "assigned"
    CONFLICT = "conflict"
    RESERVED = "reserved"


_GLYPHS: dict[PinState, str] = {
    PinState.FREE: "○",
    PinState.CANDIDATE: "◆",
    PinState.ASSIGNED: "◉",
    PinState.CONFLICT: "✗",
    PinState.RESERVED: "▣",
}


@dataclass(frozen=True, slots=True)
class PinRow:
    """One render row of the :class:`PinoutWidget`."""

    pin: PinView
    state: PinState
    holder: str | None = None
    note: str | None = None

    @property
    def glyph(self) -> str:
        return _GLYPHS[self.state]


class PinoutMode(StrEnum):
    COMPACT = "compact"
    SCHEMATIC = "schematic"


_SCHEMATIC_MIN_WIDTH = 100


class PinoutWidget(Widget):
    """Render every pin of a device with its current state.

    *Compact mode* is a vertical list — one Static per pin.
    *Schematic mode* mirrors the package outline; today we render
    a labelled ASCII rectangle.  Per-package perimeter layouts
    (LQFP / QFN / WLCSP) land with the alloy-codegen package
    registry.
    """

    DEFAULT_CSS: ClassVar[str] = """
    PinoutWidget {
        height: auto;
    }
    PinoutWidget .pin-row {
        height: 1;
    }
    PinoutWidget .pin-state-free { color: $secondary; }
    PinoutWidget .pin-state-candidate { color: $accent; text-style: bold; }
    PinoutWidget .pin-state-assigned { color: $success; }
    PinoutWidget .pin-state-conflict { color: $error; text-style: bold; }
    PinoutWidget .pin-state-reserved { color: $warning; }
    """

    def __init__(
        self,
        rows: Iterable[PinRow] = (),
        *,
        package: PackageView | None = None,
        mode: PinoutMode = PinoutMode.COMPACT,
        terminal_width: int = 120,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self._rows: tuple[PinRow, ...] = tuple(rows)
        self._package: PackageView | None = package
        self._mode = mode if terminal_width >= _SCHEMATIC_MIN_WIDTH else PinoutMode.COMPACT
        self._terminal_width = terminal_width

    @property
    def mode(self) -> PinoutMode:
        return self._mode

    @property
    def rows(self) -> tuple[PinRow, ...]:
        return self._rows

    @property
    def package(self) -> PackageView | None:
        return self._package

    def compose(self) -> ComposeResult:
        with Vertical():
            if self._mode is PinoutMode.SCHEMATIC and self._terminal_width >= _SCHEMATIC_MIN_WIDTH:
                yield from self._compose_schematic()
            else:
                yield from self._compose_compact()

    def _compose_compact(self) -> ComposeResult:
        if not self._rows:
            yield Static("[dim]No pins for this device package.[/dim]")
            return
        for row in self._rows:
            holder = f"  ← {row.holder}" if row.holder else ""
            note = f"  ({row.note})" if row.note else ""
            yield Static(
                f"  {row.glyph} {row.pin.name:<8} #{row.pin.number:<3}{holder}{note}",
                classes=f"pin-row pin-state-{row.state.value}",
            )

    def _compose_schematic(self) -> ComposeResult:
        if self._package is None:
            # Devices that don't expose a PackageView fall back to a
            # minimal ASCII placeholder — preserves the F3 contract
            # without crashing on partial data.
            yield from self._compose_schematic_fallback()
            return
        layout = pick_layout(self._package)
        cells = layout.cells(self._package)
        if not cells:
            yield from self._compose_schematic_fallback()
            return

        # Title bar mirrors CubeMX's package legend.
        yield Static(
            f"[bold]{self._package.name.upper()}[/bold] "
            f"({self._package.kind} · {self._package.pin_count} pads)"
        )

        by_row: dict[int, list[PinoutCell]] = defaultdict(list)
        for cell in cells:
            by_row[cell.row].append(cell)

        cell_width = max(12, min(self._terminal_width // 8, 18))
        for row_idx in sorted(by_row):
            row_cells = sorted(by_row[row_idx], key=lambda c: c.column)
            line = self._render_row(row_cells, cell_width=cell_width)
            yield Static(line, classes="pin-row")

    def _compose_schematic_fallback(self) -> ComposeResult:
        if not self._rows:
            yield Static("[dim]No pin layout available.[/dim]")
            return
        height = min(len(self._rows), 24)
        yield Static("┌" + "─" * 30 + "┐")
        for row in self._rows[:height]:
            label = f"{row.glyph} {row.pin.name:<6}"
            yield Static(
                f"│ {label:<28} │",
                classes=f"pin-row pin-state-{row.state.value}",
            )
        yield Static("└" + "─" * 30 + "┘")

    def _render_row(
        self, row_cells: list[PinoutCell], *, cell_width: int
    ) -> str:
        """Pack the cells of one logical row into a fixed-pitch string."""
        pin_to_row = {row.pin.name: row for row in self._rows}
        chunks: list[str] = []
        last_col = 0
        for cell in row_cells:
            gap = " " * (max(0, cell.column - last_col) * cell_width)
            text = self._format_cell(cell, pin_to_row.get(cell.pin_id))
            chunks.append(gap + text.ljust(cell_width))
            last_col = cell.column + 1
        return "".join(chunks)

    def _format_cell(self, cell: PinoutCell, row: PinRow | None) -> str:
        """Render one pad — pad number + glyph + pin name."""
        if row is None:
            # Power / ground / unbonded pads — show kind hint when present.
            tag = (cell.pad_kind or cell.pin_id or "·").upper()[:3]
            return f"{cell.pad_label} ▣ {tag}"
        return f"{cell.pad_label} {row.glyph} {row.pin.name}"

    def set_rows(self, rows: Iterable[PinRow]) -> None:
        self._rows = tuple(rows)
        self.refresh(recompose=True)

    def set_package(self, package: PackageView | None) -> None:
        self._package = package
        self.refresh(recompose=True)

    def toggle_mode(self) -> None:
        if self._terminal_width < _SCHEMATIC_MIN_WIDTH:
            return  # F3 is a no-op when the terminal is too narrow.
        self._mode = (
            PinoutMode.SCHEMATIC if self._mode is PinoutMode.COMPACT else PinoutMode.COMPACT
        )
        self.refresh(recompose=True)


def rows_from_ir(
    ir: DeviceIR,
    *,
    candidates: frozenset[str] | set[str] = frozenset(),
    assignments: dict[str, str] | None = None,
) -> tuple[PinRow, ...]:
    """Project the device IR's pin list to :class:`PinRow`s.

    ``candidates`` is the set of pins that legally drive the active
    signal — they get the CANDIDATE state if not already assigned.
    ``assignments`` maps pin → holder name; assigned pins outrank
    candidates.
    """
    out: list[PinRow] = []
    holders = assignments or {}
    for pin in ir.pins:
        if pin.name in holders:
            out.append(PinRow(pin=pin, state=PinState.ASSIGNED, holder=holders[pin.name]))
            continue
        if pin.name in candidates:
            out.append(PinRow(pin=pin, state=PinState.CANDIDATE))
            continue
        out.append(PinRow(pin=pin, state=PinState.FREE))
    return tuple(out)


__all__ = [
    "PinRow",
    "PinState",
    "PinoutMode",
    "PinoutWidget",
    "rows_from_ir",
]
