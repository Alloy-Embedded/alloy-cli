# tui-experience Specification

## Purpose
TBD - created by archiving change add-tui-foundation. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL provide a Textual app shell with global keybindings

The `alloy_cli.tui` package SHALL ship a `TuiApp` Textual
application class with a documented set of global keybindings
that work on every screen: `Ctrl+P` opens the command palette;
`?` opens a contextual help overlay; `q` quits with confirmation
when there are unsaved changes.  Every screen MUST use the shared
`DiffModal` before applying any filesystem mutation; no screen
SHALL silently write files.

#### Scenario: Ctrl+P opens command palette from any screen

- **WHEN** the user is on the Dashboard, Board Picker, or
  Peripheral Add screen
- **AND** the user presses `Ctrl+P`
- **THEN** the global Command Palette modal SHALL appear focused
- **AND** SHALL list all registered screens + recent events as
  fuzzy-searchable entries

#### Scenario: q with unsaved changes prompts to confirm

- **WHEN** the user has changes in a peripheral editor that have
  not been applied
- **AND** the user presses `q`
- **THEN** a confirmation modal SHALL appear ("Discard changes?
  [Y/N]")
- **AND** `N` SHALL keep the user on the current screen

### Requirement: TUI screens SHALL respect NO_COLOR and TERM=dumb

The TUI SHALL render without ANSI colour escapes when the environment
sets `NO_COLOR=1` or `TERM=dumb`, MUST replace colour-encoded state
with the documented glyph set (`✓ ✗ ◉ ○ ◆ ►`), SHALL still expose
every keybinding from the colour mode, and SHALL NOT reduce
information density relative to colour mode.

#### Scenario: NO_COLOR=1 produces colourless output

- **WHEN** `NO_COLOR=1` is exported and the user runs `alloy ui`
- **THEN** the output SHALL contain zero ANSI colour escapes
- **AND** SHALL still display state via `✓ ✗ ◉ ○ ◆ ►` glyphs
- **AND** every keybinding from the colour mode SHALL still work

### Requirement: alloy-cli SHALL provide a project Dashboard screen

The Dashboard SHALL be the default landing screen when `alloy` is
run inside a configured project (or `alloy ui` is invoked).  It
SHALL surface the chosen board / device, toolchain + probe status,
clock profile, peripherals list, last build summary, memory usage
mini-bar, and a recent-activity log.  It SHALL expose hotkeys for
build / flash / debug / add / clocks / memory.

#### Scenario: Dashboard renders all panels for a fully-configured project

- **WHEN** the user runs `alloy` (no args) inside a project with
  4 peripherals, a successful last build, and 3 events in the
  activity log
- **THEN** the Dashboard SHALL render with all five panels
  (peripherals, build, memory, activity, top status)
- **AND** every keybinding from the hotkey row SHALL be functional
- **AND** the snapshot SHALL match the golden file

#### Scenario: Dashboard handles empty project gracefully

- **WHEN** the user runs `alloy ui` inside a project with zero
  peripherals and no prior build
- **THEN** the peripherals panel SHALL show "No peripherals yet.
  Press 'a' to add one."
- **AND** the build panel SHALL show "Never built.  Press 'b'."

### Requirement: alloy-cli SHALL provide an onboarding wizard for new users

The Onboarding wizard SHALL guide a new user from "no project" to
"buildable project" in at most six steps: name → board → clock
profile → starter peripheral (optional) → diff confirmation →
build (optional).  Every step SHALL be skippable; partial state
SHALL be persistable to a `.alloy/onboarding.json` so the user
can resume.

#### Scenario: Onboarding wizard completes without skipping

- **WHEN** the user runs `alloy new` with no flags in an empty
  directory
- **AND** completes all six steps
- **THEN** a project tree SHALL be created with the chosen board,
  clock profile, and one peripheral
- **AND** the Dashboard SHALL open automatically afterwards

### Requirement: alloy-cli SHALL provide an interactive Board Picker screen

The `BoardPickerScreen` SHALL render a faceted browser of boards
backed by `core.search.boards`.  It SHALL combine free-text search,
filter chips (vendor, ISA, has-feature, tier), a scrollable list,
and a live-updating detail pane.  The screen SHALL be embeddable
inside the onboarding wizard as a modal-style step that returns the
selected `BoardSummary` to its caller.

#### Scenario: Searching narrows the visible list

- **WHEN** the user is on `BoardPickerScreen` with full catalogue
- **AND** the user types `nucleo` into the search field
- **THEN** the visible list SHALL contain only boards matching
  `nucleo` (fuzzy)
- **AND** the count indicator SHALL update (e.g., "showing 4/11")

#### Scenario: Detail pane updates on selection

- **WHEN** the user navigates the list with `↑↓`
- **THEN** the detail pane SHALL re-render with the highlighted
  board's full `BoardManifest` immediately (no perceptible lag)

#### Scenario: Enter returns a selection

- **WHEN** the user presses `Enter` with a board highlighted
- **THEN** the screen SHALL pop, returning the selected
  `BoardSummary` to the caller
- **AND** in the onboarding wizard, the next step SHALL receive
  this value

### Requirement: alloy-cli SHALL provide a CubeMX-class peripheral assignment TUI

The `PeripheralAddScreen` SHALL render a `PinoutWidget` showing
every pin of the device's chosen package along with each pin's
state (free / candidate for the active signal / already assigned /
reserved).  The screen SHALL provide live validation against
`core.peripherals.add_<kind>` on every field change, SHALL refuse
to enable the apply button while any validation row is failing,
and SHALL show a diff preview before any filesystem mutation.

#### Scenario: Adding UART highlights candidate pins

- **WHEN** the user opens `alloy add uart` (TUI mode) on
  `nucleo_g071rb`
- **AND** USART1 is selected as the peripheral
- **THEN** the PinoutWidget SHALL highlight every pin in
  `connection_candidates[(*, USART1_TX)]` and
  `connection_candidates[(*, USART1_RX)]` as candidate (magenta ◆)
- **AND** PA9 (one such candidate) SHALL be visually distinct from
  PA0 (free but not a candidate)

#### Scenario: Live validation prevents bad apply

- **WHEN** the user manually types `PA12` into the TX field
- **AND** PA12 is not in `connection_candidates[(PA12, USART1_TX)]`
  for the current device
- **THEN** the ValidationPanel SHALL show a red row referencing
  PA12
- **AND** the `Ctrl+S` apply binding SHALL be disabled

#### Scenario: Diff preview before apply

- **WHEN** the user has a valid configuration in the screen
- **AND** presses `Ctrl+D`
- **THEN** the DiffModal SHALL open showing the unified diff for
  `alloy.toml` and `src/peripherals.cpp`
- **AND** pressing `Y` SHALL apply both changes atomically
- **AND** pressing `N` SHALL return to the editor unchanged

#### Scenario: PinoutWidget toggles compact / schematic with F3

- **WHEN** the screen is open in compact mode (default)
- **AND** the user presses `F3`
- **THEN** the PinoutWidget SHALL re-render in schematic mode
  (ASCII-art chip outline with pin labels around perimeter)
- **AND** the `F3` press SHALL be a no-op when terminal width is
  below 100 columns (compact mode forced)

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

### Requirement: alloy-cli SHALL provide TUI screens for DMA matrix and memory map

The `DmaMatrixScreen` SHALL render a peripheral × channel grid
with the existing bindings highlighted, conflict cells flagged,
and inline bind / unbind interactions.  The `MemoryMapScreen`
SHALL render flash and RAM regions as stacked-bar visualisations
driven by IR `memories[]` plus the last `.elf` map file, with a
per-section breakdown panel.

#### Scenario: DMA matrix displays current bindings

- **WHEN** the user opens `tui.screens.DmaMatrixScreen` on a
  project with `USART1_TX → DMA1_CH1` and `USART1_RX → DMA1_CH2`
- **THEN** the matrix cell at row USART1_TX × column ch1 SHALL
  show ● (bound)
- **AND** the cell at row USART1_RX × column ch2 SHALL show ●
- **AND** all other cells SHALL show ◯ (available) or be empty
  for incompatible (peripheral, channel) pairs

#### Scenario: Memory map reports flash usage

- **WHEN** the user opens `tui.screens.MemoryMapScreen` after a
  successful build that produced a 32 KB ELF on a 128 KB device
- **THEN** the flash bar SHALL show 25% used
- **AND** the section breakdown SHALL list `.text`, `.rodata`,
  `.data`, `.bss` sizes from the linker `.map` file

### Requirement: ClockTreeScreen SHALL persist user overrides as named profiles

`tui.screens.ClockTreeScreen` SHALL bind `Ctrl+S` to a save flow
that captures the current override map as a `ClockProfileBody`,
prompts for a name (defaulting to `custom_<timestamp>`), shows a
DiffModal preview against `alloy.toml`, and on confirmation
persists the profile via `core.clocks.save_profile`.  The screen
SHALL refuse to save when the name is empty or duplicates an
existing profile.  Pressing `p` SHALL cycle through every saved
profile plus a `(custom)` label for unsaved edits.

#### Scenario: Ctrl+S persists the live override as a new profile

- **WHEN** the user has overridden PLL to 96 MHz on the screen
- **AND** presses `Ctrl+S`
- **AND** confirms the diff with name `dev_low_power`
- **THEN** `alloy.toml` SHALL gain a
  `[clocks.profiles.dev_low_power]` block with the PLL N / R and
  derived rates
- **AND** the validation panel SHALL be empty of error rows

#### Scenario: p cycles named profiles plus the unsaved (custom) entry

- **WHEN** `[clocks].profiles` has entries `default_pll_64mhz`
  and `dev_low_power`
- **AND** the user has unsaved overrides on the screen
- **THEN** pressing `p` repeatedly SHALL cycle through
  `default_pll_64mhz`, `dev_low_power`, `(custom)` and back
- **AND** the visible rate column SHALL update to match the
  selected profile's body

### Requirement: alloy-cli SHALL ship a Textual DoctorScreen with re-run and auto-fix

The `tui.screens.DoctorScreen` SHALL render the diagnostic report
returned by `core.diagnose.run()` as a navigable `DataTable` with
one row per check.  The screen SHALL bind `r` to a full re-run,
`f` to applying the highlighted row's auto-fix (when one is
registered), `Enter` to a per-row detail panel, and `Esc` to
close.  The Dashboard's `d` binding SHALL push the new screen
instead of emitting the placeholder notification it shows today.

#### Scenario: Doctor screen lists every check with the right glyph

- **WHEN** the user opens DoctorScreen with the alloy-devices-yml
  submodule uninitialised
- **THEN** the table SHALL contain a row for `alloy-devices-yml`
  with severity warning, the install hint, and an auto-fix
  available indicator
- **AND** rows for cmake / ninja / arm-none-eabi-gcc / probe-rs
  SHALL each render their detection state with the paired glyph

#### Scenario: pressing f runs the highlighted auto-fix

- **WHEN** the user highlights the `alloy-devices-yml` row
- **AND** presses `f`
- **THEN** the screen SHALL invoke the registered auto-fix
- **AND** the row SHALL update in place with the new outcome
  (success → severity info + ✓ glyph; failure → severity error +
  the captured stderr tail)

#### Scenario: rows without an auto-fix ignore f

- **WHEN** the highlighted row has `auto_fix = None`
- **AND** the user presses `f`
- **THEN** the screen SHALL emit a notification stating no
  auto-fix is available
- **AND** the table SHALL remain unchanged

