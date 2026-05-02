# project-format Specification

## Purpose
TBD - created by archiving change define-project-format. Update Purpose after archive.
## Requirements
### Requirement: alloy projects SHALL be described by an `alloy.toml` schema-locked manifest

Every `alloy-cli` project SHALL declare its configuration in a
single `alloy.toml` file at the project root.  The file SHALL
validate against the JSON Schema shipped at
`schema/alloy_toml_v1.json` (Draft 2020-12).  The manifest SHALL
support a `[project]` block, exactly one of `[board]` or `[chip]`,
optional `[clocks]`, zero or more `[[peripherals]]`, and optional
`[build]` / `[flash]` blocks.  The schema MUST carry a top-level
`schema_version` field for future migration.

#### Scenario: Valid alloy.toml parses into ProjectConfig

- **WHEN** `alloy_cli.core.project.read("alloy.toml")` is called on
  a fixture with `[project]` + `[board]` + one `[[peripherals]]
  kind="gpio"` block
- **THEN** the result SHALL be a `ProjectConfig` with the
  peripheral typed as `GpioPeripheral`
- **AND** the round-trip `write → read` SHALL produce the same
  primitive structure

#### Scenario: Invalid alloy.toml surfaces a precise error

- **WHEN** `read()` is called on an `alloy.toml` whose
  `[[peripherals]]` block has `kind = "uart"` but no `tx` field
- **THEN** the call SHALL raise `ProjectConfigError`
- **AND** the error message SHALL include the JSON path
  (`peripherals[0].tx`) and the violated constraint
  ("required when kind=uart")

### Requirement: alloy.toml SHALL declare schema version for migration

Every `alloy.toml` SHALL include a `schema_version = "1.0.0"`
field (or higher).  Reading a manifest with an older minor version
SHALL succeed.  Reading a manifest with a higher major version
SHALL fail with a "this alloy-cli is too old" error pointing at
`alloy update`.

#### Scenario: Higher major version refuses to load

- **WHEN** an `alloy.toml` declares `schema_version = "2.0.0"` and
  `alloy-cli` only knows v1.x
- **THEN** `read()` SHALL raise `ProjectConfigVersionError`
- **AND** the error SHALL mention "upgrade alloy-cli"

### Requirement: alloy.toml schema SHALL enforce per-kind sub-schemas for timer / pwm / adc / dac / can / usb / eth

The JSON Schema at `schema/alloy_toml_v1_1.json` SHALL extend the
v1.0 contract additively: every `[[peripherals]]` entry whose
`kind` is one of `timer / pwm / adc / dac / can / usb / eth` SHALL
validate against a kind-specific block defining required fields
and enum-valued options.  Files declaring `schema_version =
"1.0.x"` SHALL continue to load unchanged; the `_check_schema_version`
helper SHALL accept both `1.0.x` and `1.1.x`.

#### Scenario: schema_version 1.1.0 enables timer kind validation

- **WHEN** the user writes a `[[peripherals]]` block with
  `kind = "timer"` and `schema_version = "1.1.0"` in `alloy.toml`
- **AND** the entry omits the required `period_ns` field
- **THEN** `core.project.read` SHALL raise `ProjectConfigError`
  with a message referencing `peripherals[*].period_ns`

#### Scenario: schema_version 1.0.0 still loads under the new validator

- **WHEN** the user has `schema_version = "1.0.0"` and a
  `[[peripherals]] kind = "uart"` entry that was valid under the
  previous schema
- **THEN** `core.project.read` SHALL succeed without warnings
- **AND** the resulting `ProjectConfig` SHALL be byte-identical
  on round-trip

