## ADDED Requirements

### Requirement: All façades SHALL render typed errors via the AlloyCliError contract

Every code path under `src/alloy_cli/` SHALL replace bare
`except Exception` catches with a narrow exception list whose
recoverable cases are rethrown as a subclass of
`alloy_cli.core.errors.AlloyCliError`.  The CLI Click runner,
the Textual app, and the MCP tool registry SHALL each render
those typed errors with their stable `error_type` so users see
actionable messages instead of generic "something went wrong"
text.  Suppressed exceptions (the few legitimate cases where
re-raising would crash the TUI) SHALL be routed through
`core.log.get_logger(...)` so a maintainer can grep
`.alloy/cache/alloy-cli.log` after the fact.

#### Scenario: an uninitialised submodule surfaces a structured diagnostic

- **WHEN** the user runs `alloy add uart console` in a checkout
  whose `data/devices/` submodule is missing
- **THEN** the CLI SHALL exit with the stable code mapped from
  `DataRepoMissingError`
- **AND** the printed message SHALL include the
  `git submodule update --init` install hint

#### Scenario: TUI peripheral-add surfaces the typed error in a notification

- **WHEN** the user opens the peripheral-add screen against a
  board whose chip YAML is missing
- **THEN** the screen SHALL emit a `notify(severity="error")`
  whose body matches the `DeviceNotFoundError.error_type`
- **AND** a corresponding `ERROR` line SHALL land in
  `.alloy/cache/alloy-cli.log`

#### Scenario: ruff BLE001 lint stays green

- **WHEN** CI runs `ruff check src tests` with `BLE001`
  enabled
- **THEN** the run SHALL exit zero
- **AND** no `# noqa: BLE001` markers SHALL be required

### Requirement: Structured log is rotation-bounded and tmp-overridable

`core.log.get_logger(name)` SHALL append to
`.alloy/cache/alloy-cli.log` by default and SHALL roll once the
file passes 1 MB, retaining a single `.1` backup.  The
`ALLOY_CLI_LOG` environment variable SHALL override the file
path so the test suite can pin it to a tmp directory.

#### Scenario: log rotates after 1 MB

- **WHEN** `.alloy/cache/alloy-cli.log` already weighs 1 MB and
  another log line is emitted
- **THEN** the existing file SHALL be renamed to
  `alloy-cli.log.1`
- **AND** the new line SHALL land in a freshly-opened
  `alloy-cli.log` whose size is below 1 MB
