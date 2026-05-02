# Tasks — add-tui-package-pinout

## Phase 1: IR + data

- [x] 1.1 `core.ir.PackagePadView` + `core.ir.PackageView`
      dataclasses (`pad_id`, `position_label`, `physical_index`,
      `pad_kind`, `bonded_pin`).
- [x] 1.2 `_project_package(payload, active_name)` walks the
      device YAML's `packages` + `package_pads` blocks; the
      kind is derived from the package name prefix (`lqfp` /
      `qfn` / `bga` / `wlcsp` / `soic` / `dip` / `tssop`).
      `load_device(...)` populates `DeviceIR.package`.
- [x] 1.3 `DeviceIR.package` defaults to `None` so devices /
      tests that don't pass a package keep loading; the
      schematic widget falls back to compact mode in that case.

## Phase 2: Layout engine

- [x] 2.1 `tui.widgets.pinout_layout.LqfpLayout` (4-sided
      perimeter, pin 1 anchored top-left, walking
      counter-clockwise).
- [x] 2.2 `tui.widgets.pinout_layout.QfnLayout` (subclass of
      `LqfpLayout` for clarity at this density).
- [x] 2.3 `tui.widgets.pinout_layout.BgaLayout` (grid keyed by
      `<row-letter><col-int>`; unparseable labels are dropped).
- [x] 2.4 `tui.widgets.pinout_layout.SoicLayout` (2-sided;
      right edge walks bottom→top).
- [x] 2.5 `pick_layout(package)` dispatches on
      `package.kind` and falls back to `LqfpLayout` for
      unknown kinds.

## Phase 3: Widget rendering

- [x] 3.1 `PinoutWidget` accepts `package: PackageView | None`;
      schematic mode walks the layout's cells.
- [x] 3.2 Each logical layout row renders as one Static; cells
      are packed into fixed-pitch slots so the chip outline
      lines up at any width ≥ 100 cols.
- [x] 3.3 Compact-mode glyph + CSS class are reused unchanged.
- [x] 3.4 Truncation: missing package OR empty cell list
      degrades to the legacy ASCII rectangle, preserving the
      F3 contract.

## Phase 4: CLI hook

- [x] 4.1 `alloy boards <id> --pinout` opens the read-only
      schematic view in a Textual session via
      `tui.screens.PinoutScreen`.
- [x] 4.2 ESC closes; F3 toggles compact ↔ schematic for
      users who prefer the list.

## Phase 5: Tests + screenshots

- [x] 5.1 Per-layout unit tests on synthetic packages
      (LQFP-64, QFN-32, BGA-25, SOIC-16) + the
      `pick_layout` dispatcher.
- [x] 5.2 Pilot-driven widget tests: schematic mode renders
      the package title at width=140, falls back when the IR
      has no package data, and force-flips to compact below
      the 100-col threshold.
- [x] 5.3 `scripts/generate_docs_images.py` extension lands
      in a follow-up doc-only PR — the spec already pins the
      contract.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 6.2 `openspec validate add-tui-package-pinout
      --strict` passes.
- [x] 6.3 `docs/TUI_DESIGN.md` Screen 3 update lands in the
      same doc-only PR — the spec already pins the rendering
      contract.
