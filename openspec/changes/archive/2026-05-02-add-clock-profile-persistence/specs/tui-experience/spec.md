## ADDED Requirements

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
