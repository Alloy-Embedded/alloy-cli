## ADDED Requirements

### Requirement: alloy debug SHALL launch a Textual front-end by default and fall back to the wrapper on demand

`alloy debug` SHALL detect a TTY and, when present, launch
`tui.screens.DebugScreen` against a `core.gdb.GdbSession`
attached to a freshly-spawned `probe-rs gdb-server`.  The
existing wrapper behaviour (spawn server + launch the user's
configured GDB front-end) SHALL remain accessible via
`--no-tui`.  Multi-probe disambiguation SHALL reuse
`core.flash.detect_probes` so the user picks once.

#### Scenario: alloy debug on a TTY opens the DebugScreen

- **WHEN** the user runs `alloy debug` on a TTY with a
  single probe attached
- **THEN** the CLI SHALL spawn `probe-rs gdb-server` on a
  fresh port
- **AND** SHALL push `tui.screens.DebugScreen` connected to
  that server
- **AND** SHALL NOT launch a separate GDB front-end

#### Scenario: --no-tui keeps the wrapper

- **WHEN** the user runs `alloy debug --no-tui`
- **THEN** the CLI SHALL spawn `probe-rs gdb-server` AND
  the user's configured GDB front-end (env var
  `ALLOY_GDB` or the default
  `arm-none-eabi-gdb`)
- **AND** the Textual screen SHALL NOT be launched

#### Scenario: --port overrides the gdb-server port

- **WHEN** the user runs `alloy debug --port 4321`
- **THEN** the spawned gdb-server SHALL bind to port 4321
- **AND** the DebugScreen SHALL connect to that port
