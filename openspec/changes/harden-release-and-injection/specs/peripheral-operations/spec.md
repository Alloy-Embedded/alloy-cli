## ADDED Requirements

### Requirement: alloy.toml SHALL be emitted by a single canonical writer

`core.project.dumps(config) -> str` SHALL be the only function
that turns a `ProjectConfig` into TOML text.  `core.project.write`
SHALL delegate to `dumps`; the diff path in `core.peripherals`
SHALL consume `dumps` instead of duplicating the emit logic.
The previous `core.peripherals._emit_toml` SHALL be deleted.

#### Scenario: dumps round-trips through read

- **WHEN** a `ProjectConfig` is serialised via
  `core.project.dumps(config)`
- **AND** the result is parsed back via `core.project.read`
- **THEN** the resulting `ProjectConfig` SHALL be byte-identical
  on a second `dumps` pass
- **AND** the diff path in `core.peripherals.add_*` SHALL render
  identical before / after text whether it builds the strings
  via `dumps` or via the old internal helper
