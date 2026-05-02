## MODIFIED Requirements

### Requirement: alloy-cli SHALL diagnose the host environment via `alloy doctor`

The `alloy doctor` command SHALL aggregate checks across Python
runtime, toolchains, probes, project validity, network, and
alloy component versions.  When the project under inspection (or
the `--for <family>` override) resolves a known family manifest,
doctor SHALL render the per-family tool list described in that
manifest and SHALL omit tools the family does not require.  When
no family resolves (no `alloy.toml`, no `--for`, or an unknown
family id), doctor SHALL fall back to the legacy generic check
list (cmake, ninja, arm-none-eabi-gcc, probe-rs).

The rendered table SHALL include a `source` column showing where
each tool would come from: `system` (already on PATH), `xpack`,
`github:<owner>/<repo>`, `probe-rs-installer`, `espressif`, or
`vendor (EULA — install manually)`.  Vendor-source missing tools
SHALL be reported with `severity="info"` (never `error`) and the
`install_hint` field SHALL contain the per-OS doc URL drawn from
the manifest's `install_docs` block.

The command SHALL emit a Rich-formatted human report by default
and JSON via `--json`.  The JSON output SHALL bump
`schema_version` to `"1.1"` and SHALL add a `source` key to each
check entry (`null` for non-toolchain checks).  It SHALL offer
auto-fixers for safe issues (pip-install missing deps, init
submodule); it SHALL NEVER auto-install system toolchains, only
print the install command (in this wave; Wave 2 lifts that
constraint for non-vendor sources).

#### Scenario: doctor reports a missing toolchain with install hint

- **WHEN** `arm-none-eabi-gcc` is not on `PATH`
- **AND** the user runs `alloy doctor` outside any project
- **THEN** the report SHALL flag `arm-none-eabi-gcc` as missing
- **AND** SHALL include the OS-specific install command
- **AND** SHALL exit non-zero (signals a remediable issue)

#### Scenario: doctor inside a stm32g0 project shows only stm32g0 tools

- **WHEN** the user's `alloy.toml` resolves to family `stm32g0`
- **AND** the user runs `alloy doctor`
- **THEN** the rendered table SHALL include rows for
  `arm-none-eabi-gcc`, `cmake`, `ninja`, and `probe-rs`
- **AND** the table SHALL NOT include rows for `xtensa-esp-elf-gcc`,
  `esptool`, or any tool unique to other families
- **AND** the table SHALL include a `source` column populated for
  every tool row

#### Scenario: --for esp32 lists the esp32 tool set without a project

- **WHEN** the user runs `alloy doctor --for esp32` from a
  directory with no `alloy.toml`
- **THEN** the report SHALL list `xtensa-esp-elf-gcc`, `esptool`,
  `cmake`, and `ninja`
- **AND** SHALL NOT list `arm-none-eabi-gcc`
- **AND** the `source` column SHALL show `espressif` for
  `xtensa-esp-elf-gcc` and `github:espressif/esptool` for
  `esptool`

#### Scenario: vendor-source missing tools render as info, not error

- **WHEN** `STM32CubeProgrammer` is missing on a stm32f4 project
- **AND** the user runs `alloy doctor`
- **THEN** the row SHALL show `severity="info"`
- **AND** the `install_hint` SHALL contain the per-OS doc URL
- **AND** the `source` column SHALL read
  `vendor (EULA — install manually)`
- **AND** doctor SHALL NOT exit non-zero solely because of vendor
  tool absence

#### Scenario: --json reflects the new source field

- **WHEN** the user runs `alloy doctor --json`
- **THEN** the top-level `schema_version` SHALL be `"1.1"`
- **AND** every check entry SHALL contain a `source` key
- **AND** the value SHALL be `null` for non-toolchain checks
  (e.g. `alloy.toml`, `accessibility-suite`)

#### Scenario: unknown --for value fails clearly

- **WHEN** the user runs `alloy doctor --for nonexistent`
- **THEN** the command SHALL exit non-zero
- **AND** stderr SHALL list the available family ids
- **AND** SHALL suggest checking the doc set for adding a new
  family manifest
