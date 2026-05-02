## ADDED Requirements

### Requirement: alloy-cli SHALL regenerate codegen headers as part of `alloy build`

The `alloy build` command SHALL invoke alloy-codegen before cmake
whenever the codegen entry point is discoverable.  The codegen
output SHALL land under `.alloy/generated/<device>/include/` and
the resulting build SHALL link against those headers.  A stamp
file under `.alloy/generated/<device>/.stamp` SHALL key the cache
on `(ir_sha, codegen_version, alloy_cli_version)`; codegen SHALL
NOT re-run while the stamp is current.  When the alloy-codegen
package is not installed the build SHALL log a warning and
continue without the codegen step so existing CI flows remain
green.

#### Scenario: alloy build refreshes generated headers when the stamp is stale

- **WHEN** the user runs `alloy build` with no
  `.alloy/generated/<device>/.stamp` present
- **THEN** the build SHALL invoke `alloy_codegen.generate(...)` once
- **AND** SHALL write a stamp file capturing the IR SHA, codegen
  version, and alloy-cli version
- **AND** the resulting `BuildResult.codegen_returncode` SHALL be 0
- **AND** the cmake / ninja steps SHALL run after codegen succeeds

#### Scenario: alloy build skips codegen when the stamp is fresh

- **WHEN** the user runs `alloy build` twice in a row with no
  changes to alloy.toml or the device IR
- **THEN** the second build SHALL set `BuildResult.codegen_skipped`
  to True
- **AND** the contents of `.alloy/generated/<device>/include/`
  SHALL be byte-identical to the first build's output

#### Scenario: alloy build --regen forces codegen even when the stamp is fresh

- **WHEN** the user runs `alloy build --regen`
- **THEN** the codegen step SHALL run regardless of stamp state
- **AND** `BuildResult.codegen_skipped` SHALL be False

#### Scenario: alloy build without alloy-codegen installed degrades gracefully

- **WHEN** alloy-codegen is not importable in the current Python
  environment
- **AND** the user runs `alloy build`
- **THEN** the command SHALL log a warning naming alloy-codegen as
  the missing dependency
- **AND** the build SHALL proceed to the cmake / ninja steps using
  whatever headers exist under `.alloy/generated/`
- **AND** `BuildResult.codegen_returncode` SHALL be `None`
