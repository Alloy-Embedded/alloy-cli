## ADDED Requirements

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
