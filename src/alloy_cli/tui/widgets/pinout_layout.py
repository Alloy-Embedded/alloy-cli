"""Per-package layout strategies for the schematic pinout view.

Each strategy converts a :class:`core.ir.PackageView` into a flat
list of :class:`PinoutCell` records keyed by ``(row, column)``.
The widget then renders one Static per row, packing the cells into
fixed-width slots.

Strategies are intentionally pure data — no Textual / rich imports
— so they can be unit-tested without spinning up an app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from alloy_cli.core.ir import PackagePadView, PackageView


@dataclass(frozen=True, slots=True)
class PinoutCell:
    """One renderable pad in the schematic grid.

    ``row`` / ``column`` are 0-based logical coordinates the widget
    walks in render order; concrete values depend on the layout
    strategy.  ``side`` is purely informational ("left", "right",
    "top", "bottom", "grid") so the renderer can colour the chip
    edges differently.
    """

    row: int
    column: int
    pin_id: str
    pad_label: str
    side: str
    pad_kind: str | None = None


class PerimeterLayout(Protocol):
    """Strategy for converting a package + pad list into cells."""

    def cells(self, package: PackageView) -> tuple[PinoutCell, ...]: ...


# ---------------------------------------------------------------------------
# 4-sided layouts (LQFP / QFN)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LqfpLayout:
    """4-sided perimeter — pin 1 at top-left, walking counter-clockwise.

    Convention: pin 1 is on the top edge, the index walks
    counter-clockwise (down the left edge first), matching CubeMX's
    common LQFP orientation.  We split the pads into four equal
    sides; if ``pin_count`` is not divisible by 4 the remaining
    pads spill onto the bottom edge.
    """

    name: str = "lqfp"

    def cells(self, package: PackageView) -> tuple[PinoutCell, ...]:
        pads = sorted(package.pads, key=lambda p: p.physical_index)
        n = max(package.pin_count, len(pads))
        if n == 0:
            return ()
        per_side = n // 4
        left_end = per_side
        bottom_end = 2 * per_side
        right_end = 3 * per_side
        out: list[PinoutCell] = []
        for pad in pads:
            idx = pad.physical_index
            if idx <= 0:
                continue
            zero_idx = idx - 1  # 0-based
            if zero_idx < left_end:
                side = "left"
                row = 1 + zero_idx
                column = 0
            elif zero_idx < bottom_end:
                side = "bottom"
                offset = zero_idx - left_end
                row = per_side + 1
                column = 1 + offset
            elif zero_idx < right_end:
                side = "right"
                offset = zero_idx - bottom_end
                row = per_side - offset
                column = per_side + 1
            else:
                side = "top"
                offset = zero_idx - right_end
                row = 0
                # Top edge walks right-to-left as we close the
                # counter-clockwise loop back to pin 1.
                column = max(1, per_side - offset)
            out.append(_cell(pad, row=row, column=column, side=side))
        return tuple(out)


@dataclass(frozen=True, slots=True)
class QfnLayout(LqfpLayout):
    """QFN packages share the LQFP perimeter geometry at this density."""

    name: str = "qfn"


# ---------------------------------------------------------------------------
# 2-sided layouts (SOIC / DIP / TSSOP)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SoicLayout:
    """2-sided perimeter — pin 1 top-left, walking counter-clockwise.

    Half the pins go down the left side (top → bottom), the other
    half walk back up the right side (bottom → top).  Used for
    SOIC, DIP, and TSSOP packages.
    """

    name: str = "soic"

    def cells(self, package: PackageView) -> tuple[PinoutCell, ...]:
        pads = sorted(package.pads, key=lambda p: p.physical_index)
        n = max(package.pin_count, len(pads))
        if n == 0:
            return ()
        half = n // 2
        out: list[PinoutCell] = []
        for pad in pads:
            idx = pad.physical_index
            if idx <= 0:
                continue
            if idx <= half:
                side = "left"
                row = idx - 1
                column = 0
            else:
                side = "right"
                # Right side walks bottom → top; the pin number
                # opposite pin 1 is the highest on the right edge.
                row = n - idx
                column = 1
            out.append(_cell(pad, row=row, column=column, side=side))
        return tuple(out)


# ---------------------------------------------------------------------------
# Grid layouts (BGA / WLCSP)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BgaLayout:
    """Grid layout for BGA / WLCSP — balls keyed by ``[A-Z][0-9]+``.

    The pad's ``position_label`` is parsed as ``<row-letter><col-int>``
    (e.g. ``A1``, ``F12``).  Pads that don't match the pattern are
    dropped — a future improvement can fall back to ``physical_index``
    for non-standard labels.
    """

    name: str = "bga"

    def cells(self, package: PackageView) -> tuple[PinoutCell, ...]:
        out: list[PinoutCell] = []
        for pad in package.pads:
            label = pad.position_label or pad.pad_id
            row, col = _parse_grid_label(label)
            if row is None or col is None:
                continue
            out.append(_cell(pad, row=row, column=col, side="grid"))
        return tuple(out)


def _parse_grid_label(label: str) -> tuple[int | None, int | None]:
    if not label:
        return (None, None)
    label = label.strip().upper()
    # Letter prefix: usually one char (A-Y, skipping I/O), occasionally two (AA, AB).
    letter_end = 0
    while letter_end < len(label) and label[letter_end].isalpha():
        letter_end += 1
    if letter_end == 0 or letter_end == len(label):
        return (None, None)
    letters = label[:letter_end]
    digits = label[letter_end:]
    try:
        col = int(digits) - 1
    except ValueError:
        return (None, None)
    row = 0
    for ch in letters:
        row = row * 26 + (ord(ch) - ord("A") + 1)
    return (row - 1, col)


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


def pick_layout(package: PackageView) -> PerimeterLayout:
    """Return the right strategy for ``package.kind``.

    Falls back to :class:`LqfpLayout` for unknown kinds — the
    perimeter convention degrades gracefully even when the package
    isn't formally one of the supported families.
    """
    kind = (package.kind or "").lower()
    if kind in ("lqfp",):
        return LqfpLayout()
    if kind in ("qfn",):
        return QfnLayout()
    if kind in ("bga", "wlcsp"):
        return BgaLayout()
    if kind in ("soic", "dip", "tssop"):
        return SoicLayout()
    return LqfpLayout()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cell(pad: PackagePadView, *, row: int, column: int, side: str) -> PinoutCell:
    return PinoutCell(
        row=row,
        column=column,
        pin_id=pad.bonded_pin or "",
        pad_label=pad.pad_id or pad.position_label,
        side=side,
        pad_kind=pad.pad_kind,
    )


__all__ = [
    "BgaLayout",
    "LqfpLayout",
    "PerimeterLayout",
    "PinoutCell",
    "QfnLayout",
    "SoicLayout",
    "pick_layout",
]
