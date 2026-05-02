## ADDED Requirements

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
