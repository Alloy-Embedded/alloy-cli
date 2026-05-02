## ADDED Requirements

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
