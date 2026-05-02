# Tasks — add-tui-peripheral-assignment

## Phase 1: PinoutWidget

- [ ] 1.1 `tui.widgets.PinoutWidget` — compact mode (vertical
      list, one row per pin number).
- [ ] 1.2 PinoutWidget — schematic mode (ASCII-art chip outline
      with pin labels around perimeter).  LQFP / QFN / WLCSP
      layouts via `IR.packages[].name` lookup.
- [ ] 1.3 Per-row rendering: pin number, state glyph (◉/◆/►/✗/▣),
      pin name, current assignment text.
- [ ] 1.4 Candidate highlighting: when a peripheral signal is
      being added, magenta-mark every pin whose
      `connection_candidates[(pin, signal)]` exists.
- [ ] 1.5 Conflict highlighting: red-mark pins that conflict with
      existing peripherals.
- [ ] 1.6 Search/filter: `/` filters list to candidates only.
- [ ] 1.7 Snapshot tests: 3 packages × 2 modes = 6 goldens.

## Phase 2: PeripheralAddScreen layout

- [ ] 2.1 `tui.screens.PeripheralAddScreen(kind: PeripheralKind)`
      — supports uart / gpio / spi / i2c / timer / pwm / adc /
      can / dma / dac / rtc / watchdog / qspi / sdmmc / usb /
      eth.
- [ ] 2.2 Header: peripheral selector (radio over free instances)
      + `name` text input.
- [ ] 2.3 Body: PinoutWidget at top, then per-kind config fields
      (TX/RX dropdowns, DMA toggle + channel selector, baud /
      prescaler / mode, etc.).
- [ ] 2.4 ValidationPanel docked at bottom — live updates.
- [ ] 2.5 Footer: "Will modify: alloy.toml + src/peripherals.cpp"
      with diff-line counts.

## Phase 3: Smart defaults wiring

- [ ] 3.1 On screen mount: pre-fill from
      `core.suggestions.suggest_*`.
- [ ] 3.2 On any field change: re-run validation, re-render
      panel, update apply-button enable state.
- [ ] 3.3 Live diff preview: panel shows up-to-date
      `core.peripherals.add_<kind>(...).diff` on every change.

## Phase 4: Apply flow

- [ ] 4.1 `Ctrl+D` opens DiffModal with the proposed diff.
- [ ] 4.2 `Ctrl+S` applies (calls `core.emit.write(diff)` to
      atomic-replace the affected files).
- [ ] 4.3 On success: transition back to Dashboard with a toast.
- [ ] 4.4 On failure: surface error via DiffModal; never
      silently swallow.

## Phase 5: Snapshot tests

- [ ] 5.1 UART pinout (compact + schematic) + validation panel.
- [ ] 5.2 SPI with NSS-software vs hardware.
- [ ] 5.3 I²C with conflict (existing peripheral).
- [ ] 5.4 GPIO with all defaults.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 6.2 `openspec validate add-tui-peripheral-assignment
      --strict` passes.
- [ ] 6.3 Manual smoke on three real boards (nucleo_g071rb,
      pico, esp32-c3).
