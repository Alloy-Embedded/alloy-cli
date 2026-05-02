# Add TUI Peripheral Assignment

## Why

**This is the killer screen.**  The one that decides whether
`alloy-cli` is taken seriously.  CubeMX has the GUI version that
ST users have loved for 15 years; we ship the same density and
quality in the terminal — for **8 500+ chips**, type-validated,
scriptable, AI-callable.

See `docs/TUI_DESIGN.md` Screen 3 for the full design.

## What Changes

- **`tui.screens.PeripheralAddScreen`** — full layout per Screen 3.
- **`tui.widgets.PinoutWidget`** — the most important custom
  widget.  Two render modes (compact list / schematic chip), each
  showing pin number, glyph, name, current state, candidate
  highlighting.  Driven by `connection_candidates` from the IR.
- **`tui.widgets.ValidationPanel`** (from foundation) wired to
  show live validation against `core.peripherals.add_*` with
  every keystroke.
- Wraps `core.peripherals.add_*` from
  `add-cli-add-peripheral`.  All validation logic lives there;
  the TUI only renders + collects input.
- Per-kind body: same template (Peripheral selector → pins →
  DMA → format) with kind-specific fields (uart baud / spi
  prescaler / i2c speed / etc.).
- `Ctrl+D` opens DiffModal; `Ctrl+S` applies (only enabled when
  validation panel has zero red rows).
- `F3` toggles compact ↔ schematic pinout view.
- `F4` opens the DMA Matrix (Phase 5) as a drill-down.

## Impact

The first time a user sees this screen we either win them for
years or lose them forever.  Ship it at CubeMX-density, ship it
keyboard-fast, ship it correct via IR validation.

## What this DOES NOT do

- Does not implement `add_*` operations — those are in
  `add-cli-add-peripheral`.  This proposal **only** ships the TUI.
- No DMA matrix as a fully-featured screen (Phase 5).
- No memory-map drill-down (Phase 5).
- No AI-suggested layout — that's the MCP path.
- No "peripheral remove" — defer.
