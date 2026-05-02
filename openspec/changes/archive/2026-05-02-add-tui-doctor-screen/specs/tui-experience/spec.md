## ADDED Requirements

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
