## ADDED Requirements

### Requirement: alloy-cli SHALL list and search boards and devices

The `alloy boards` and `alloy devices` commands SHALL surface the
catalogues backed by `alloy/boards/*/board.json` and
`alloy-devices-yml` respectively.  Both SHALL support free-text
search (matching board_id / mcu / vendor / family / device-name),
faceted filters (vendor, ISA, has-feature, tier), JSON output for
scripting, and a positional detail mode (`alloy boards <id>`,
`alloy devices <name>`).

#### Scenario: alloy boards lists all admitted boards

- **WHEN** the user runs `alloy boards`
- **THEN** the command SHALL exit 0
- **AND** SHALL list every board found in the resolved alloy SDK
  catalogue (currently 11+)
- **AND** the output SHALL include columns for board_id, mcu,
  vendor, family, ISA, tier

#### Scenario: alloy boards --search filters by query

- **WHEN** the user runs `alloy boards --search nucleo`
- **THEN** the result SHALL contain only boards whose board_id /
  mcu / vendor matches `nucleo` (fuzzy)
- **AND** results SHALL be ranked by best match first

#### Scenario: alloy boards --json emits stable schema

- **WHEN** the user runs `alloy boards --json`
- **THEN** stdout SHALL be a single JSON document with shape
  `{"schema_version":"1.0", "boards":[BoardSummary...]}`
- **AND** each `BoardSummary` SHALL contain `board_id`, `mcu`,
  `vendor`, `family`, `core`, `flash_size_bytes`,
  `clock_profiles`, `tier`

#### Scenario: alloy devices --all includes bulk-admitted chips

- **WHEN** the user runs `alloy devices --all --vendor st`
- **THEN** the result SHALL include both `vendors/st/...` and
  `bulk-admitted/.../st/...` devices
- **AND** results SHALL be tagged `admitted=true|false`
