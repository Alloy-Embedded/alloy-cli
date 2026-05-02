## ADDED Requirements

### Requirement: alloy.toml SHALL support a [clocks].profiles map

The `alloy.toml [clocks]` block SHALL accept an optional
`profiles` table mapping profile name → profile body, where the
body declares `source`, `pll_n`, `pll_r`, `sysclk_hz`, `hclk_div`,
`apb1_div`, `apb2_div`, and an open `extras` dict.  The validator
SHALL reject duplicate names and SHALL ensure `[clocks].profile`
references an existing key when both are present.

#### Scenario: a saved profile round-trips through read + write

- **WHEN** `alloy.toml [clocks].profiles.dev_low_power` is present
  with `pll_n = 24`, `pll_r = 2`, `sysclk_hz = 96_000_000`
- **THEN** `core.project.read` SHALL surface the body in the
  `ProjectConfig.clocks` payload
- **AND** `core.project.write` SHALL emit the same TOML bytes on
  round-trip

#### Scenario: [clocks].profile referencing an unknown name fails validation

- **WHEN** the user writes `[clocks].profile = "fast"` but the
  `[clocks].profiles` map has no `fast` key
- **THEN** `core.project.read` SHALL raise `ProjectConfigError`
  with the missing profile name in the message
