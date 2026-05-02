"""Tests for ``add-tui-package-pinout`` (#19).

Phase 5 covers:

- Per-layout unit tests on synthetic packages (LQFP-64, QFN-32,
  BGA-25, SOIC-16) (5.1).
- Pilot-driven widget test: schematic mode renders with the
  package title visible at width=140 (5.2).
- CLI: ``alloy boards <id> --pinout`` plumbing — flag exists,
  refuses to run without a board id (5.3).
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from alloy_cli.core.ir import (
    DeviceIdentity,
    DeviceIR,
    PackagePadView,
    PackageView,
    PinView,
)
from alloy_cli.main import cli
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.widgets.pinout import (
    PinoutMode,
    PinoutWidget,
    rows_from_ir,
)
from alloy_cli.tui.widgets.pinout_layout import (
    BgaLayout,
    LqfpLayout,
    QfnLayout,
    SoicLayout,
    pick_layout,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pad(idx: int, *, package: str, pin: str | None, kind: str = "io") -> PackagePadView:
    return PackagePadView(
        pad_id=str(idx),
        package=package,
        position_label=str(idx),
        physical_index=idx,
        pad_kind=kind,
        bonded_pin=pin,
    )


def _bga_pad(label: str, *, package: str, pin: str | None) -> PackagePadView:
    return PackagePadView(
        pad_id=label,
        package=package,
        position_label=label,
        physical_index=0,
        pad_kind="io",
        bonded_pin=pin,
    )


def _lqfp64() -> PackageView:
    pads = tuple(_pad(i, package="lqfp64", pin=f"P{i:02d}") for i in range(1, 65))
    return PackageView(name="lqfp64", kind="lqfp", pin_count=64, pads=pads)


def _qfn32() -> PackageView:
    pads = tuple(_pad(i, package="qfn32", pin=f"P{i:02d}") for i in range(1, 33))
    return PackageView(name="qfn32", kind="qfn", pin_count=32, pads=pads)


def _bga25() -> PackageView:
    rows = ("A", "B", "C", "D", "E")
    pads = tuple(
        _bga_pad(f"{r}{c}", package="bga25", pin=f"{r}{c}")
        for r in rows
        for c in range(1, 6)
    )
    return PackageView(name="bga25", kind="bga", pin_count=25, pads=pads)


def _soic16() -> PackageView:
    pads = tuple(_pad(i, package="soic16", pin=f"P{i:02d}") for i in range(1, 17))
    return PackageView(name="soic16", kind="soic", pin_count=16, pads=pads)


# ---------------------------------------------------------------------------
# Phase 5.1 — layout unit tests
# ---------------------------------------------------------------------------


def test_lqfp_layout_distributes_pads_around_four_sides() -> None:
    layout = LqfpLayout()
    cells = layout.cells(_lqfp64())
    by_side: dict[str, list[int]] = {}
    for cell in cells:
        by_side.setdefault(cell.side, []).append(int(cell.pad_label))
    # 64 pins ÷ 4 = 16 per side.
    assert sorted(by_side["left"]) == list(range(1, 17))
    assert sorted(by_side["bottom"]) == list(range(17, 33))
    assert sorted(by_side["right"]) == list(range(33, 49))
    assert sorted(by_side["top"]) == list(range(49, 65))


def test_lqfp_layout_pin_one_anchors_top_left() -> None:
    layout = LqfpLayout()
    cells = {int(c.pad_label): c for c in layout.cells(_lqfp64())}
    # Pin 1 anchors the top-left corner — column 0, row 1.
    assert cells[1].column == 0
    assert cells[1].row == 1
    # Pin 16 is the last pin on the left edge.
    assert cells[16].side == "left"
    # Pin 17 starts the bottom edge.
    assert cells[17].side == "bottom"


def test_qfn_layout_uses_same_perimeter_as_lqfp() -> None:
    pkg = _qfn32()
    qfn_cells = QfnLayout().cells(pkg)
    # Translate each cell into a (side, label) tuple to compare
    # against an LqfpLayout run on the same package.
    qfn_pairs = sorted((c.side, c.pad_label) for c in qfn_cells)
    lqfp_pairs = sorted(
        (c.side, c.pad_label) for c in LqfpLayout().cells(pkg)
    )
    assert qfn_pairs == lqfp_pairs


def test_bga_layout_maps_letter_digit_to_grid() -> None:
    layout = BgaLayout()
    cells = {c.pad_label: c for c in layout.cells(_bga25())}
    # A1 → (row=0, col=0); E5 → (row=4, col=4).
    assert (cells["A1"].row, cells["A1"].column) == (0, 0)
    assert (cells["E5"].row, cells["E5"].column) == (4, 4)
    assert all(cell.side == "grid" for cell in cells.values())


def test_bga_layout_skips_unparseable_labels() -> None:
    bad = PackageView(
        name="weird",
        kind="bga",
        pin_count=2,
        pads=(
            _bga_pad("A1", package="weird", pin="A1"),
            PackagePadView(
                pad_id="bogus",
                package="weird",
                position_label="not-a-label",
                physical_index=0,
                pad_kind="io",
                bonded_pin=None,
            ),
        ),
    )
    cells = BgaLayout().cells(bad)
    # Only A1 survives; the bogus label is dropped silently.
    labels = {c.pad_label for c in cells}
    assert labels == {"A1"}


def test_soic_layout_splits_into_two_sides() -> None:
    layout = SoicLayout()
    cells = {int(c.pad_label): c for c in layout.cells(_soic16())}
    assert cells[1].side == "left"
    assert cells[8].side == "left"
    assert cells[9].side == "right"
    assert cells[16].side == "right"
    # Right side walks bottom→top — pin 9 is at the bottom of the
    # right edge, pin 16 anchors the top.
    assert cells[9].row > cells[16].row


def test_pick_layout_dispatches_on_kind() -> None:
    assert isinstance(pick_layout(_lqfp64()), LqfpLayout)
    assert isinstance(pick_layout(_qfn32()), QfnLayout)
    assert isinstance(pick_layout(_bga25()), BgaLayout)
    assert isinstance(pick_layout(_soic16()), SoicLayout)
    # Unknown kinds fall through to the LQFP perimeter strategy.
    assert isinstance(
        pick_layout(PackageView(name="?", kind="exotic", pin_count=0, pads=())),
        LqfpLayout,
    )


# ---------------------------------------------------------------------------
# Phase 5.2 — widget pilot test
# ---------------------------------------------------------------------------


def _ir_with(package: PackageView | None) -> DeviceIR:
    return DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32g0",
            device="stm32g071rb",
            package="lqfp64",
            core="cortex-m0plus",
            summary="STM32G0",
        ),
        peripherals=(),
        pins=tuple(
            PinView(name=f"P{i:02d}", port=None, number=i) for i in range(1, 65)
        ),
        connection_candidates=(),
        dma_routes=(),
        clock_nodes=(),
        package=package,
        payload={},
    )


@pytest.mark.asyncio
async def test_pinout_widget_renders_schematic_with_package_title() -> None:
    ir = _ir_with(_lqfp64())
    widget = PinoutWidget(
        rows_from_ir(ir, candidates=frozenset({"P21"})),
        package=ir.package,
        mode=PinoutMode.SCHEMATIC,
        terminal_width=140,
    )
    app = TuiApp(initial_screen=_HostScreen(widget))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        # The first Static carries the title bar with the package name.
        statics = [str(node.render()) for node in widget.query("Static")]
        assert any("LQFP64" in s for s in statics)
        # Pin 21 + its candidate glyph are visible somewhere in the
        # rendered output.
        assert any("21" in s and "P21" in s for s in statics)


@pytest.mark.asyncio
async def test_pinout_widget_falls_back_when_no_package() -> None:
    ir = _ir_with(None)
    widget = PinoutWidget(
        rows_from_ir(ir),
        package=None,
        mode=PinoutMode.SCHEMATIC,
        terminal_width=140,
    )
    app = TuiApp(initial_screen=_HostScreen(widget))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        # The fallback path renders the legacy ASCII rectangle —
        # the title bar with the package name should NOT appear.
        rendered = "\n".join(str(node.render()) for node in widget.query("Static"))
        assert "┌──" in rendered  # ASCII box drawn
        assert "LQFP64" not in rendered


@pytest.mark.asyncio
async def test_pinout_widget_compact_mode_when_terminal_narrow() -> None:
    ir = _ir_with(_lqfp64())
    widget = PinoutWidget(
        rows_from_ir(ir),
        package=ir.package,
        mode=PinoutMode.SCHEMATIC,
        terminal_width=80,  # below the 100-col threshold
    )
    # The constructor force-flips schematic → compact below the
    # threshold, regardless of the requested mode.
    assert widget.mode is PinoutMode.COMPACT


# ---------------------------------------------------------------------------
# Phase 5.3 — CLI surface
# ---------------------------------------------------------------------------


def test_alloy_boards_pinout_help_advertises_flag() -> None:
    result = CliRunner().invoke(cli, ["boards", "--help"])
    assert result.exit_code == 0
    assert "--pinout" in result.output


def test_alloy_boards_pinout_without_id_errors() -> None:
    result = CliRunner().invoke(cli, ["boards", "--pinout"])
    # Click translates ClickException into exit_code 1.
    assert result.exit_code == 1
    assert "--pinout requires a board id" in result.output


# ---------------------------------------------------------------------------
# IR-level loader regression
# ---------------------------------------------------------------------------


def test_device_ir_package_field_defaults_to_none() -> None:
    """Devices that don't pass a package keep DeviceIR.package = None."""
    ir = DeviceIR(
        identity=DeviceIdentity(
            vendor="x", family="y", device="z", package="", core="", summary=""
        ),
        peripherals=(),
        pins=(),
        connection_candidates=(),
        dma_routes=(),
        clock_nodes=(),
        payload={},
    )
    assert ir.package is None


def test_project_package_returns_none_without_packages_block() -> None:
    """The loader skips the package projection when YAML has no packages."""
    from alloy_cli.core.ir import _project_package

    assert _project_package({}, "lqfp64") is None


def test_project_package_extracts_kind_from_name() -> None:
    from alloy_cli.core.ir import _project_package

    payload = {
        "packages": [{"name": "ufqfpn32", "pin_count": 32}],
        "package_pads": [
            {
                "pad_id": "1",
                "package": "ufqfpn32",
                "position_label": "1",
                "physical_index": 1,
                "pad_kind": "io",
                "bonded_pin": "PA0",
            }
        ],
    }
    pkg = _project_package(payload, "ufqfpn32")
    assert pkg is not None
    assert pkg.kind == "qfn"
    assert pkg.pin_count == 32
    assert len(pkg.pads) == 1
    assert pkg.pads[0].bonded_pin == "PA0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


from textual.app import ComposeResult  # noqa: E402
from textual.containers import Vertical  # noqa: E402
from textual.screen import Screen  # noqa: E402


class _HostScreen(Screen[None]):
    """Trivial screen that mounts a single widget — used by pilot tests."""

    def __init__(self, widget: PinoutWidget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self._widget
