## ADDED Requirements

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
