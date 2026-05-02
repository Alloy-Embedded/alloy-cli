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

