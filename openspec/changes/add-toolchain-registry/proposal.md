## Why

Today `alloy doctor` checks one hard-coded toolchain list (cmake, ninja,
arm-none-eabi-gcc, probe-rs) regardless of the project's MCU.  An ESP32
project sees a misleading "✗ arm-none-eabi-gcc missing" while a STM32
project sees no warning that `STM32CubeProgrammer` is the right recovery
tool.  The user is left to figure out which tools they actually need,
where to download them, and how to resolve PATH conflicts when multiple
versions coexist.

This proposal lays the **data and parser foundation** for a per-MCU-family
toolchain map.  No downloads, no installs land in this wave — those are
Waves 2-4.  Wave 1 is the schema, the manifests for the top five
families, and a family-aware `alloy doctor`.  Without it, the later
waves have nothing to install *from*.

## What Changes

- New JSON Schema `schema/family_toolchain_v1.json` (Draft 2020-12)
  describing a per-family toolchain manifest: `required`,
  `recommended`, `optional` tool lists, each with a source
  (`xpack | github:<owner>/<repo> | probe-rs-installer | espressif | vendor`),
  version range, capabilities, and Linux `udev_required` flag.
- New `data/families/` tree shipping initial manifests:
  `arm-cortex-m.yml` (shared base), `stm32f4.yml`, `stm32g0.yml`,
  `rp2040.yml`, `nrf52.yml`, `esp32.yml`.  Each manifest declares a
  `schema_version: "1.0.0"` top-level field and may `extends:` another
  family to dedupe shared tools.
- New core module `alloy_cli.core.toolchain_registry` with typed views
  (`FamilyManifest`, `ToolRequirement`) and pure functions
  `load_family(family_id)`, `resolve_for_project(config)`.  On-disk
  cache mirrors the IR cache pattern (SHA-keyed pickle under
  `.alloy/cache/families/`).
- `alloy_cli.core.diagnose.run` gains a `family: str | None = None`
  parameter.  When a family resolves (from `[chip].family`,
  `boards.lookup(board.id).family`, or the explicit override), doctor
  reports only that family's tool list.  When none resolves, it falls
  back to today's generic check list — no regression for users without
  a project context.
- `CheckResult` gains `source: str | None` so the doctor table renders
  *where* each tool comes from ("xpack", "system", "vendor (EULA)").
  Vendor-source missing tools surface as `severity="info"` with an
  install-doc URL — never as an error block, since we cannot
  redistribute EULA-gated binaries.
- `alloy doctor` gains a `--for <family_id>` flag for inspecting any
  family before scaffolding (when no `alloy.toml` exists yet).
- New MCP tool `alloy.list_family_toolchain(family_id)` returning the
  manifest as JSON for LLM agents.
- New error type `FamilyToolchainError` (subclass of `AlloyCliError`)
  with `error_type="family-toolchain-error"` for invalid manifests
  (unknown family, broken `extends:` chain, schema violations).
- New documentation: `docs/TOOLCHAIN_REGISTRY.md` explains the
  manifest schema for contributors; `docs/ERROR_COOKBOOK.md` gains
  the `FamilyToolchainError` anchor.

## Capabilities

### New Capabilities

- `toolchain-management`: per-family toolchain manifests, family
  resolution from project config, family-aware diagnostics, and the
  contract that later waves (download/install, onboarding wizard,
  recovery tools) will extend.

### Modified Capabilities

- `cli-surface`: `alloy doctor` adds the `--for <family>` flag and
  the `source` column in its rendered table; without `--for`, output
  shape changes only when the project pins a family that has a
  manifest.
- `mcp-surface`: a new `alloy.list_family_toolchain(family_id)` tool
  is exposed alongside the existing read-only tool set.
- `developer-experience`: the error cookbook gains an anchor for
  `FamilyToolchainError`; a new `docs/TOOLCHAIN_REGISTRY.md` is
  added to the contributor docs.

## Impact

- **New code**: `src/alloy_cli/core/toolchain_registry.py`,
  `src/alloy_cli/data/families/*.yml` (shipped via hatch wheel
  shared-data), `schema/family_toolchain_v1.json`.
- **Modified code**: `src/alloy_cli/core/diagnose.py` (add `family`
  parameter, family-aware checks, `source` field),
  `src/alloy_cli/core/errors.py` (add `FamilyToolchainError`),
  `src/alloy_cli/commands/doctor.py` (add `--for` flag, render
  `source` column), `src/alloy_cli/mcp/tools.py` (register
  `list_family_toolchain`), `pyproject.toml` (ship the schema +
  manifests as package data).
- **Dependencies**: no new runtime dependencies.  `jsonschema` and
  `pyyaml` are already pinned for the alloy.toml + IR loaders.
- **Backward compatibility**: fully backward-compatible.  Projects
  without a family-mapped target see the legacy generic check list;
  the existing JSON output schema for `alloy doctor` adds the
  `source` field as a new optional key (`schema_version` bumped to
  `1.1`).
- **Out of scope (Waves 2-4)**: actual downloads via xPack /
  Espressif / GitHub; the content-addressed tool store; the
  `alloy toolchain install/list/use/prune` command group; the
  `alloy new` post-scaffold install prompt; `alloy reset`,
  `alloy erase`, `alloy monitor`; EULA-gated guided detection
  beyond the link rendering this wave already provides.
