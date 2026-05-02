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

### Requirement: PinoutWidget SHALL render the device's actual package outline in schematic mode

`tui.widgets.PinoutWidget` SHALL produce a perimeter rendering of
the device's package whenever the IR exposes a `PackageView`.
The layout engine SHALL pick a per-kind strategy (LQFP / QFN /
WLCSP / BGA / SOIC / DIP) and place each pin at its physical
position around the chip outline.  Pin state glyphs (free /
candidate / assigned / conflict / reserved) SHALL render in situ
next to the corresponding pin label.  The widget SHALL fall back
to compact mode when either (a) the terminal is narrower than
100 columns or (b) the device IR exposes no `PackageView`.

#### Scenario: schematic mode draws the LQFP perimeter

- **WHEN** the user opens the Peripheral Add screen on
  `nucleo_g071rb` (LQFP-64) at terminal width 140
- **AND** F3 toggles the pinout to schematic mode
- **THEN** the rendered widget SHALL contain four sides of the
  chip outline with pin numbers labelled along each edge
- **AND** PA9 (a USART1 TX candidate) SHALL render adjacent to
  pin 21 of the LQFP-64 footprint with the candidate (◆) glyph

#### Scenario: schematic mode falls back when the IR has no package data

- **WHEN** the user opens the screen on a device whose IR exposes
  `package = None`
- **THEN** the widget SHALL render compact mode regardless of the
  user's F3 toggle preference
- **AND** a notification SHALL inform the user that the schematic
  view is unavailable for this device

#### Scenario: alloy boards <id> --pinout opens a read-only schematic view

- **WHEN** the user runs `alloy boards nucleo_g071rb --pinout`
- **THEN** a Textual session SHALL open the schematic view of the
  board's chip
- **AND** ESC SHALL close the session without writing any files

### Requirement: TUI screens SHALL be pinned with SVG snapshot tests

Every Textual screen shipped by alloy-cli SHALL have a
corresponding SVG golden under `tests/snapshots/` that
`pytest-textual-snapshot` compares against on every run.  The
golden SHALL be regenerated via `pytest --snapshot-update` and
SHALL match byte-for-byte the SVG that the same render path
produces in `docs/images/`.  CI SHALL fail when any pinned
screen drifts; the failure SHALL print the regenerated SVG path
so reviewers can audit the diff in the PR.

#### Scenario: a screen layout regression fails CI

- **WHEN** a contributor changes `DashboardScreen.compose` so
  that the toolchain row drops a pill
- **AND** the snapshot test runs without `--snapshot-update`
- **THEN** the test SHALL fail with a non-zero exit code
- **AND** the failure message SHALL name the affected SVG and
  the command to refresh it
- **AND** the contributor SHALL be able to inspect the diff via
  `git diff tests/snapshots/02-dashboard.svg`

#### Scenario: docs/images stays in sync with the snapshot goldens

- **WHEN** the snapshot tests pass for every pinned screen
- **AND** `python scripts/generate_docs_images.py` is rerun
- **THEN** the SVGs under `docs/images/` SHALL match their
  counterparts in `tests/snapshots/` byte-for-byte

### Requirement: Every shipped screen SHALL render correctly under NO_COLOR, TERM=dumb, 16-colour, and 80-column constraints

`tests/test_accessibility_themes.py` SHALL parametrise every
pinned TUI screen across the four modes
(default, `NO_COLOR=1`, `TERM=dumb`, 16-colour) and SHALL
compare each render against an SVG golden under
`tests/snapshots/accessibility/<screen>-<mode>.svg`.  The
suite SHALL fail when any state-bearing cell relies on
colour alone (no glyph paired).  A separate suite SHALL
re-render every screen at `size=(80, 30)` and SHALL fail
when content overflows the 80-column ceiling.

#### Scenario: NO_COLOR render still surfaces every pin state

- **WHEN** Pilot runs the PeripheralAddScreen with
  `NO_COLOR=1`
- **THEN** the rendered SVG SHALL contain every state's
  glyph (`○`, `◆`, `◉`, `✗`, `▣`)
- **AND** SHALL NOT rely on colour fills to distinguish the
  states

#### Scenario: 80-column layout doesn't truncate critical content

- **WHEN** the Dashboard renders at `size=(80, 30)`
- **THEN** every Static under the toolchain row SHALL fit
  within 80 columns
- **AND** the build / memory panels SHALL fall back to a
  compact layout instead of clipping mid-line

### Requirement: Every interactive widget SHALL carry a non-empty tooltip or aria_label

`tests/test_accessibility_aria.py` SHALL walk every widget
yielded by every shipped `Screen.compose` method and assert
`widget.tooltip` or `widget.aria_label` is non-empty.  An
explicit allow-list under the test exempts purely
decorative widgets (dividers, spacers); reviewers SHALL see
the allow-list when reviewing PRs that change widget
composition.

#### Scenario: a new widget without a tooltip fails CI

- **WHEN** a contributor lands a `Button("Save")` without
  setting `tooltip="…"` or `aria_label="…"`
- **AND** the button is not in the decorative allow-list
- **THEN** `tests/test_accessibility_aria.py` SHALL fail
- **AND** the failure message SHALL name the screen, the
  widget id (or text), and link to the allow-list comment

### Requirement: alloy doctor SHALL surface an accessibility-suite informational check

`core.diagnose.run` SHALL include an
`accessibility-suite` check whose `severity` is `"info"`
and whose `message` summarises the active terminal's
`NO_COLOR`, `TERM`, and `COLORTERM` values.  The check SHALL
NOT have an auto-fix; the message SHALL link to the
accessibility section of `docs/CONTRIBUTING.md` (or the
followup quickstart) when something looks suspicious.

#### Scenario: TERM=dumb surfaces in doctor output

- **WHEN** the user runs `alloy doctor` with
  `TERM=dumb` exported
- **THEN** the report SHALL contain a row whose `name` is
  `accessibility-suite`
- **AND** the row's message SHALL include the literal
  string `TERM=dumb`

### Requirement: DebugScreen SHALL render the canonical 5-panel debugger view backed by a GDB MI2 session

`tui.screens.DebugScreen` SHALL mount five panels in a 2×3
grid: Source, Call stack, Locals + watches, Registers, and a
GDB-log panel.  Each panel SHALL update from a typed
`core.gdb.GdbSession` whose responses come from the MI2 wire
parser (no string scraping in the screen).  Bindings SHALL
provide `c` continue, `s` step in, `n` step over, `o` step
out, `b` toggle breakpoint, `i` interrupt, `w` add watch, and
`Esc` close.  Closing the screen SHALL tear down the
underlying gdb-server subprocess; an unexpected exit of that
subprocess SHALL surface a typed error notification.

#### Scenario: stepping into a function refreshes Source + Call stack + Locals

- **WHEN** the user presses `s` while paused at
  `main.c:42`
- **THEN** the Source panel SHALL update to the called
  function's first line
- **AND** the Call stack panel SHALL gain a new top frame
- **AND** the Locals panel SHALL render the called
  function's locals

#### Scenario: probe-rs gdb-server crashes mid-session

- **WHEN** the spawned `probe-rs gdb-server` process exits
  unexpectedly
- **THEN** DebugScreen SHALL emit
  `notify(severity="error")` whose body names the captured
  stderr tail
- **AND** SHALL log an `ERROR` line to
  `.alloy/cache/alloy-cli.log`
- **AND** SHALL NOT leave the gdb-mi subprocess as an
  orphan PID after dismissing

#### Scenario: toggling a breakpoint round-trips through the GDB log

- **WHEN** the user puts the cursor on a Source line and
  presses `b`
- **THEN** the screen SHALL invoke
  `GdbSession.set_breakpoint(loc=...)`
- **AND** the GDB log panel SHALL show both the issued MI2
  command and the resulting `^done,bkpt={...}` reply
- **AND** the Source panel SHALL gain a breakpoint glyph in
  the gutter on that line

