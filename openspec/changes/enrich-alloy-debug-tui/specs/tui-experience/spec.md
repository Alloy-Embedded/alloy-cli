## ADDED Requirements

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
