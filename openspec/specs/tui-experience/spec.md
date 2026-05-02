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

