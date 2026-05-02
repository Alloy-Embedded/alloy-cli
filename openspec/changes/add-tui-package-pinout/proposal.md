# Add Per-Package Schematic Pinout Rendering

## Why

`PinoutWidget` ships a compact mode (vertical list, one row per
pin) and a "schematic" mode that today renders an ASCII rectangle
with pin labels stacked along the left edge.  CubeMX's quad-package
visualisation is the killer feature we promised in `docs/VISION.md`
and `docs/TUI_DESIGN.md` Screen 3 — pins around the package
perimeter, with state + AF labels in situ.

To deliver that in the terminal we need:

1. Per-package coordinate data (LQFP / QFN / WLCSP / BGA layouts).
2. A layout engine that plots pin numbers around the perimeter and
   places the labels without overlap inside the terminal grid.
3. A `--package` toggle so users with bigger displays can see
   higher-density layouts.

The data itself comes from alloy-devices-yml — every device YAML
already declares the package + the pin → ball/pad mapping.  We
just don't expose it in the alloy-cli IR yet.

## What Changes

### IR enrichment

- `core.ir.PackageView` dataclass: `name`, `kind in {LQFP, QFN,
  WLCSP, BGA, SOIC, DIP}`, `pin_count`, `pins:
  tuple[PackagePinView, ...]` where each `PackagePinView` carries
  the perimeter coordinate (side + index) plus the device pin id.
- `DeviceIR.package: PackageView | None` populated from the
  device YAML's `package` block on load.

### Layout engine

- `tui.widgets.pinout.layout.PerimeterLayout` — given a
  `PackageView` and the terminal width, returns a
  `tuple[PinoutCell, ...]` where each cell carries
  `(row, column, glyph, label, state, holder)`.
- Per-package strategies:
  - `LQFP / QFN` → 4 sides, label outside the chip outline.
  - `BGA / WLCSP` → grid view (rows × columns of pads).
  - `SOIC / DIP` → 2 sides.
- The strategies share a common `Cell` shape so the rendering
  code stays generic.

### Widget integration

- `PinoutWidget` switches its compose path on `mode`:
  - `compact` → today's vertical list.
  - `schematic` → renders the `PerimeterLayout` cells via a
    grid of Static widgets.
- `terminal_width >= 100` keeps schematic mode available; the
  existing F3 fallback still flips to compact when the terminal
  is too narrow.

### CLI / TUI surface

- `alloy boards <id> --pinout` opens the package view in the
  terminal (read-only) so users can browse a board without
  starting the full Peripheral Add flow.

## Impact

This is the **CubeMX-class moment** the TUI was promised on.  Pin
state, candidate highlighting, and conflict marking now show on
the actual package outline.  The Peripheral Add screen
automatically gains the new look (it already mounts
`PinoutWidget`).

## What this DOES NOT do

- Does not render board-level silkscreens (the package view is
  chip-only).
- Does not introduce a graphical (PNG / SVG) renderer — terminal
  glyphs only.
- Does not implement zoom / pan; the layout fits in a single
  screen and clips when needed.
- Does not change the widget's public API beyond the new mode
  branch.
