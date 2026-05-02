## ADDED Requirements

### Requirement: alloy-cli SHALL provide an interactive Clock Tree screen

The `ClockTreeScreen` SHALL render the device's clock graph as a
navigable node-link diagram driven by `device.clock_nodes`,
`clock_selectors`, `clock_gates`, and `peripheral_clock_bindings`.
Editing a source / PLL / selector SHALL update downstream rates
live; the screen SHALL flag rates exceeding bus maxima.  Saving
the current state as a named profile SHALL persist to
`alloy.toml [clocks]`.

#### Scenario: Editing PLL N updates SYSCLK live

- **WHEN** the user is on `ClockTreeScreen` for `stm32g071rb`
- **AND** the user changes the PLL N divisor from 16 to 32
- **THEN** the SYSCLK rate label SHALL update from `64 MHz` to
  `128 MHz` immediately
- **AND** the validation panel SHALL flag "SYSCLK 128 MHz exceeds
  device max 64 MHz" in red
- **AND** the save action SHALL be disabled

### Requirement: alloy-cli SHALL stream live build output via the BuildLogScreen

The `BuildLogScreen` SHALL stream `core.build.run_streaming(...)`
output to a Textual `RichLog` with a phase indicator (Configure /
Codegen / Compile / Link / Post-process) and a progress bar
populated from ninja's status.  Compiler diagnostics SHALL be
parsed and presented as a navigable list; `Enter` on a diagnostic
SHALL open `$EDITOR` at `<file>:<line>:<col>`.

#### Scenario: Compile error opens editor at the right line

- **WHEN** a compile error appears in the build output:
  `src/main.cpp:42:8: error: ...`
- **AND** the user navigates to that diagnostic with `↑↓` and
  presses `Enter`
- **THEN** the screen SHALL spawn `$EDITOR +42:8 src/main.cpp` (or
  the editor's equivalent line-jump syntax)

### Requirement: alloy-cli SHALL stream live flash progress via the FlashScreen

The `FlashScreen` SHALL render `core.flash.run_with_progress(...)`
output as a progress bar driven by probe-rs stderr percentage,
plus a probe identity panel and an image-preview panel.  After
successful verify the screen SHALL prompt for target reset
(default `Y`).

#### Scenario: Flash + verify completes and prompts reset

- **WHEN** flashing to a J-Link probe succeeds
- **THEN** the progress bar SHALL reach 100% and the verify phase
  SHALL display ✓
- **AND** a reset prompt with `Y/N` SHALL appear, defaulting to `Y`
- **AND** pressing `Y` SHALL trigger a target reset via probe-rs
