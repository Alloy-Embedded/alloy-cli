# Tasks — add-tui-package-pinout

## Phase 1: IR + data

- [ ] 1.1 `core.ir.PackagePinView` + `core.ir.PackageView`
      dataclasses.
- [ ] 1.2 Loader extension: `core.ir.load_device(...)` populates
      `DeviceIR.package` from the YAML's `package` block.
- [ ] 1.3 Backwards compatibility: devices that don't yet declare
      the package block load `DeviceIR.package = None` without
      raising.

## Phase 2: Layout engine

- [ ] 2.1 `tui.widgets.pinout.layout.LqfpLayout` (4-sided
      perimeter).
- [ ] 2.2 `tui.widgets.pinout.layout.QfnLayout` (same as LQFP at
      this density; sub-class for clarity).
- [ ] 2.3 `tui.widgets.pinout.layout.BgaLayout` (grid).
- [ ] 2.4 `tui.widgets.pinout.layout.SoicLayout` (2-sided).
- [ ] 2.5 Layout selector: `pick_layout(package: PackageView) ->
      PerimeterLayout`.

## Phase 3: Widget rendering

- [ ] 3.1 `PinoutWidget` schematic branch consumes the layout's
      `Cell` list.
- [ ] 3.2 Cells render via `Vertical/Horizontal` containers
      respecting cell `(row, column)`.
- [ ] 3.3 Glyph + colour pairing identical to compact mode (state
      → glyph + CSS class).
- [ ] 3.4 Truncation behaviour: when the terminal is too narrow
      for the chosen package, fall back to compact (already the
      F3 contract).

## Phase 4: CLI hook

- [ ] 4.1 `alloy boards <id> --pinout` opens a one-screen TUI
      session showing the package view (read-only).
- [ ] 4.2 ESC closes; F3 toggles compact ↔ schematic for users
      who prefer the list.

## Phase 5: Tests + screenshots

- [ ] 5.1 Per-layout unit tests on synthetic packages (LQFP-64,
      QFN-32, BGA-256).
- [ ] 5.2 Widget Pilot test: schematic mode renders with the
      chip outline visible at width=140.
- [ ] 5.3 Update `scripts/generate_docs_images.py` to ship a
      `12-package-pinout.svg` next to the existing screens.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 6.2 `openspec validate add-tui-package-pinout --strict` passes.
- [ ] 6.3 `docs/TUI_DESIGN.md` Screen 3 layout note updated to
      reflect actual per-package rendering.
