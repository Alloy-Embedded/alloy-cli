## ADDED Requirements

### Requirement: alloy-cli SHALL ship a per-family toolchain manifest schema

The repo SHALL include a JSON Schema (Draft 2020-12) at
`schema/family_toolchain_v1.json` that validates every per-MCU-family
toolchain manifest.  The schema SHALL require:

- A top-level `schema_version` matching `^1\.[0-9]+\.[0-9]+$`.
- A top-level `family_id` (kebab-case, lowercase).
- A `core` field describing the CPU core (e.g. `cortex-m4f`).
- An optional `arch` field (e.g. `armv7em`).
- An optional `extends` field naming a single parent family.
- Three optional arrays: `required[]`, `recommended[]`, and
  `optional[]`, each whose items conform to a `tool` sub-schema.

The `tool` sub-schema SHALL require:

- `tool` (string, kebab-case).
- `version` (string, semver-range — same syntax `alloy.toml` accepts).
- `source` (string) matching one of:
  `xpack`, `github:<owner>/<repo>`, `probe-rs-installer`,
  `espressif`, or `vendor`.
- `capabilities[]` (array of strings) drawn from a closed enum:
  `build`, `flash`, `debug`, `reset`, `recovery`, `serial`,
  `register-debug`.

The `tool` sub-schema SHALL allow:

- `bundles[]` (array of strings) listing extra binaries shipped
  alongside the primary tool (e.g. `arm-none-eabi-gdb` ships with
  `arm-none-eabi-gcc`).
- `udev_required` (boolean) — Linux-only hint that the tool needs
  udev rules.
- `install_docs` (object) with optional `linux`, `macos`, and
  `windows` URL strings; SHALL be required when `source = "vendor"`.

`additionalProperties` SHALL be `false` at every object level so
unknown keys fail validation immediately.

#### Scenario: the bundled schema validates the shipped manifests

- **WHEN** the test suite loads `schema/family_toolchain_v1.json`
- **AND** validates every YAML under `data/families/`
- **THEN** every shipped manifest SHALL pass validation
- **AND** mutating any required field SHALL produce a
  `jsonschema.ValidationError` flagged in CI

#### Scenario: vendor-source tools require install docs

- **WHEN** a manifest declares a tool with `source: "vendor"`
- **AND** omits the `install_docs` object
- **THEN** schema validation SHALL fail
- **AND** the failure message SHALL name the offending tool

### Requirement: alloy-cli SHALL ship initial manifests for the top five MCU families

The `data/families/` directory SHALL ship with these manifests on
the first release of this capability:

- `arm-cortex-m.yml` — shared base for ARM Cortex-M families,
  declaring `arm-none-eabi-gcc`, `cmake`, `ninja`, and `probe-rs`
  as `required`.
- `stm32f4.yml` — extends `arm-cortex-m`; declares
  `STM32CubeProgrammer` as `recommended` with `source: "vendor"`
  and per-OS `install_docs`.
- `stm32g0.yml` — extends `arm-cortex-m`; mirrors stm32f4 with
  the appropriate `core: "cortex-m0plus"`.
- `rp2040.yml` — extends `arm-cortex-m`; declares `picotool` as
  `required` with `source: "github:raspberrypi/picotool"` and
  `capabilities: ["flash", "reset"]`.
- `nrf52.yml` — extends `arm-cortex-m`; declares `nrfjprog` as
  `recommended` with `source: "vendor"` and
  `capabilities: ["recovery", "flash"]`.
- `esp32.yml` — does NOT extend arm-cortex-m; declares
  `xtensa-esp-elf-gcc` as `required` with `source: "espressif"`,
  `esptool` as `required` with `source: "github:espressif/esptool"`
  and `capabilities: ["flash", "reset", "recovery"]`.

Every manifest SHALL declare `schema_version: "1.0.0"` at the top
level.

#### Scenario: every shipped manifest loads without errors

- **WHEN** the test suite calls
  `toolchain_registry.load_family(<family_id>)` for each shipped
  manifest
- **THEN** each call SHALL return a fully-resolved `FamilyManifest`
  with non-empty `required`
- **AND** SHALL raise no exceptions

#### Scenario: stm32g0 inherits the arm-cortex-m base

- **WHEN** the test suite calls
  `toolchain_registry.load_family("stm32g0")`
- **THEN** the resolved `required` list SHALL include
  `arm-none-eabi-gcc`, `cmake`, `ninja`, and `probe-rs`
- **AND** the resolved `recommended` list SHALL include
  `STM32CubeProgrammer` from the `stm32g0.yml` overlay

### Requirement: `core.toolchain_registry` SHALL load and resolve manifests

The `alloy_cli.core.toolchain_registry` module SHALL expose typed
dataclasses (`FamilyManifest`, `ToolRequirement`) that are
`frozen=True, slots=True` and contain only JSON-friendly scalar
or tuple fields.

The module SHALL expose a pure function
`load_family(family_id: str) -> FamilyManifest` that:

- Locates the YAML under `data/families/<family_id>.yml` (or the
  packaged equivalent for installed wheels).
- Validates it against `schema/family_toolchain_v1.json`.
- Resolves the `extends:` chain by recursively loading parents.
- Merges `required / recommended / optional` arrays *by tool name*
  (child entries override base entries; absence in the child
  preserves the base entry).
- Returns the fully-flattened `FamilyManifest`.

The module SHALL expose
`resolve_for_project(config: ProjectConfig) -> FamilyManifest | None`
that returns the resolved manifest for the project's target, or
`None` when no family can be resolved.  This function SHALL NOT
raise on missing manifests; it SHALL return `None` and let the
caller fall back to a generic check list.

The module SHALL cache parsed manifests on disk under
`<repo_root>/.alloy/cache/families/<family_id>.pkl`, keyed on
`(sha256(manifest_yaml) + sha256(parent_yaml...) +
alloy_cli_version)`.  Cache misses SHALL re-parse and re-validate.

#### Scenario: load_family resolves the extends chain

- **WHEN** `load_family("stm32f4")` is called
- **AND** `stm32f4.yml` declares `extends: arm-cortex-m`
- **THEN** the returned manifest's `required` SHALL include every
  tool from both files
- **AND** if a tool name appears in both, the `stm32f4.yml` entry
  SHALL win

#### Scenario: cycles in extends raise a typed error

- **WHEN** `load_family` is called against a manifest set where
  `a.yml` extends `b.yml` and `b.yml` extends `a.yml`
- **THEN** `FamilyToolchainError` SHALL be raised with
  `error_type="family-toolchain-cycle"`
- **AND** the message SHALL list the cycle: `a → b → a`

#### Scenario: unknown parent raises a typed error

- **WHEN** a manifest declares `extends: nonexistent`
- **AND** `load_family` is called against it
- **THEN** `FamilyToolchainError` SHALL be raised with
  `error_type="family-toolchain-unknown-parent"`

#### Scenario: family resolution falls back gracefully

- **WHEN** `resolve_for_project(config)` is called
- **AND** the project's chip family has no manifest under
  `data/families/`
- **THEN** the function SHALL return `None`
- **AND** SHALL NOT raise

#### Scenario: family resolution honours [chip] over [board]

- **WHEN** an `alloy.toml` carries both `[chip]` and `[board]`
  (theoretical; today's schema disallows it, but the resolver
  remains explicit about precedence)
- **AND** `resolve_for_project(config)` is called
- **THEN** the function SHALL use `config.chip.family` and ignore
  the board

### Requirement: `FamilyToolchainError` SHALL be part of the AlloyCliError hierarchy

`alloy_cli.core.errors` SHALL export a `FamilyToolchainError`
subclass of `AlloyCliError` with the stable
`error_type = "family-toolchain-error"`.  Sub-types SHALL set the
class-level `error_type` to one of:

- `family-toolchain-cycle`
- `family-toolchain-unknown-parent`
- `family-toolchain-schema`
- `family-toolchain-not-found`

The error type contract SHALL be exercised by a test that asserts
each `error_type` string is unique across the AlloyCliError
hierarchy.

#### Scenario: every new error_type appears in the cookbook

- **WHEN** CI runs `scripts/check_error_cookbook.py`
- **THEN** the script SHALL discover every new
  `family-toolchain-*` error type
- **AND** SHALL fail when any error type lacks a matching anchor
  in `docs/ERROR_COOKBOOK.md`
