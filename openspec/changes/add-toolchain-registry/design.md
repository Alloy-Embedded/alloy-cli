## Context

`alloy doctor` today calls a hard-coded list of detectors in
`core.diagnose.run`: cmake, ninja, arm-none-eabi-gcc, probe-rs.  The
detectors live in `core.toolchain` (one function per binary), each
returning a `ToolchainStatus` with a per-OS install hint string.
There is no notion of "what does *this project* need" — an ESP32
project sees an arm-none-eabi-gcc warning, an STM32 project sees no
mention of `STM32CubeProgrammer` even though it is the canonical
recovery + DFU tool.

Three sibling assets already encode "what chip is in this project":

* `alloy.toml [chip]` carries `vendor / family / device`.
* `alloy.toml [board]` resolves through `core.boards.lookup` to a
  `BoardManifest` whose `family` field is the same string.
* `core.ir.load_device(...)` projects the canonical IR for the chip.

The IR does *not* describe host toolchains.  That coupling is wrong:
chip IR should stay vendor-neutral, while toolchain choices ("xpack
arm-gcc 14.2 vs Arm Developer 13.3") are an `alloy-cli` concern.

This proposal puts the toolchain knowledge in a *separate*
declarative tree under `data/families/`, parsed by a new
`core.toolchain_registry` module.  The tree is intentionally
shipped *with alloy-cli itself* (not the alloy-devices-yml
submodule) so a release of alloy-cli is the single source of truth
for the manifest contract that downstream waves consume.

Wave 1 stops at "describe + diagnose."  Waves 2-4 add the
installer, the onboarding wizard, and the recovery commands.

## Goals / Non-Goals

**Goals:**

- A typed, schema-validated, additive manifest format that any new
  family can adopt without code changes.
- Family resolution that works from *either* `[board]` *or* `[chip]`
  in `alloy.toml`, and from an explicit `--for <family>` flag when
  no project exists yet.
- `alloy doctor` emits a per-family checklist with a `source`
  column making it obvious which tools come from xPack, the system,
  or a vendor download.
- A clean dependency edge so Wave 2's installer can read
  `manifest.required[*].source` and dispatch to the right adapter
  without re-parsing.
- A reusable base manifest (`arm-cortex-m.yml`) so adding a new
  Cortex-M family ships a 5-line YAML, not a re-statement of
  cmake/ninja/arm-gcc/probe-rs.
- Backward compatibility: an `alloy.toml` with no resolvable family
  still produces today's generic doctor output, and the JSON
  schema for the doctor result is bumped to `1.1` with `source`
  added as an optional key.

**Non-Goals:**

- *No download or install logic.*  Wave 2 owns `tool_sources.py`
  and `toolchain_manager.py`.  This wave never makes network
  calls.
- *No PATH manipulation.*  `core.toolchain` keeps its
  `shutil.which`-based detection; the registry only adds context
  about *what should be detected*.
- *No vendor-tool detection beyond a "looks installed?" hook.*
  Detecting STM32CubeProgrammer's exact location across OSes is a
  Wave-4 concern; Wave 1 relies on the existing `which`-based
  detectors plus a `vendor_detector` callable hook the manifest
  can name (defaults to `which`).
- *No new TUI screen.*  The existing DoctorScreen consumes the
  same `DiagnosticReport` and renders the new `source` column;
  per-family dashboards are a later proposal.
- *No changes to the `alloy.toml` schema.*  The toolchain
  manifest lives in alloy-cli's package data, not in user
  projects.

## Decisions

### D1: Manifests ship inside alloy-cli, not in alloy-devices-yml

The chip IR repo intentionally describes only on-chip facts.
Toolchain choice is host-side and changes faster than IR (e.g.,
when xPack publishes a new arm-gcc).  Coupling them would force a
devices-yml release every time a toolchain pin moves.

**Alternatives considered:**

- *Embed in alloy-devices-yml under `families/`.*  Rejected: ties
  IR cadence to toolchain cadence and pollutes IR consumers
  (alloy-codegen, the C++ HAL) with host concerns they should not
  see.
- *Standalone repo `alloy-toolchains-yml`.*  Premature.  Five
  manifests of <100 lines each fit comfortably inside alloy-cli.
  We can extract later if the catalog grows past ~40 families or
  if external contributors want to ship third-party manifests.

### D2: One YAML per family + `extends:` for shared bases

Pure inheritance, not template engines.  Each manifest declares a
single optional `extends: <parent_family_id>` field; the parser
resolves the chain at load time and merges `required /
recommended / optional` arrays *by tool name* so a child family
can override a base entry.

**Alternatives considered:**

- *Jinja templating per family.*  Overpowered: makes diffs
  unreadable and breaks declarative validation.
- *Flat YAMLs with no inheritance.*  Forces every Cortex-M family
  to repeat the same arm-gcc / cmake / ninja / probe-rs lines.
- *Multiple inheritance.*  YAGNI.  Single-parent covers every
  realistic case (Cortex-M0+ extends Cortex-M, ESP32-C3 might
  extend `riscv-esp` later).  The schema can be relaxed if a
  use case emerges.

### D3: `source` is an opaque string the parser doesn't dispatch on

Wave 1 only reads `source` for display purposes.  Wave 2 builds
an adapter registry keyed on the *prefix* of the string
(`xpack`, `github:`, `probe-rs-installer`, `espressif`,
`vendor`).  Keeping the dispatcher in Wave 2 keeps Wave 1 small
and avoids over-fitting the source vocabulary before we have
real adapters to inform it.

The schema validates `source` against a `pattern`-like enum (`^(xpack|github:[a-z0-9-]+/[a-z0-9_.-]+|probe-rs-installer|espressif|vendor)$`)
so misspelled sources fail fast at manifest load time.

### D4: Vendor-source tools are info-severity, not error-severity

Surfacing STM32CubeProgrammer as `severity="error"` would push
users toward auto-fix, which we cannot perform (EULA).  Wave 1
renders them as `severity="info"` with a markdown-style
`install_doc_url` per OS resolved from
`manifest.<tool>.install_docs.{linux,macos,windows}`.

The doctor table flags the row with `source="vendor (EULA —
install manually)"`; the auto-fix column shows `-` (no fix
available) so the existing `--fix` semantics aren't misled into
trying.

### D5: Family resolution walks board → chip with explicit override

Resolution order in `resolve_for_project(config)`:

1. If `--for <family>` is on the CLI, use that and stop.
2. Else if `config.chip is not None`, use `config.chip.family`.
3. Else if `config.board is not None`, look up via
   `core.boards.lookup(config.board.id).family`.
4. Else: return `None` (caller falls back to today's generic
   check list).

`resolve_for_project` *never* raises for missing families.  An
unknown family id (resolved from a board manifest that points at a
family we don't ship a YAML for yet) raises
`FamilyToolchainError("no manifest for family X")` from
`load_family`, but `resolve_for_project` catches it and surfaces
a soft warning so a half-supported chip doesn't break `alloy
doctor` entirely.

### D6: On-disk cache mirrors the IR cache

The manifest YAML is parsed + the `extends:` chain resolved into a
fully-flat `FamilyManifest` and pickled under
`<repo_root>/.alloy/cache/families/<family_id>.pkl` keyed on
`(sha256(manifest_yaml) + sha256(parent_yaml...) +
alloy_cli_version)`.  Cache hit is sub-millisecond; cache miss is
~5 ms (one yaml.safe_load + dataclass projection).

The cache lives at the repo level, not the project level, because
the manifests are package data that doesn't change between
projects on the same alloy-cli install.

### D7: New `FamilyToolchainError` over reusing existing types

`AlloyCliError` already has `ProjectConfigError` (for `alloy.toml`
issues) and `DataRepoMissingError` (for the device YAML
submodule).  Toolchain manifest issues are conceptually
different — they're alloy-cli's own data, not user input or
external repo state.  A separate type means agents and humans can
branch on `error_type="family-toolchain-error"` without
overloading the alloy.toml namespace.

### D8: MCP `list_family_toolchain` is read-only and stateless

The new tool returns the resolved manifest as a JSON dict.  No
diff cache, no project mutation, no preview/apply flow — it is in
the same family as `list_boards` and `list_devices`.  This keeps
the LLM agent surface coherent (read tools are flat; write tools
go through `preview_diff` → `apply_diff`).

## Risks / Trade-offs

- **[Risk]** Manifest churn breaks downstream waves' contracts.
  → **Mitigation**: `schema_version: "1.0.0"` at the top of
  every manifest, JSON Schema gates additions, dataclasses use
  `frozen=True, slots=True` so accidental field additions in code
  show up in the test suite.

- **[Risk]** Five-family seed is too narrow; users on stm32h7,
  esp32-c3, samd51 see "no manifest for family X."
  → **Mitigation**: include a soft-warning code path in
  `resolve_for_project` so `alloy doctor` falls back to the
  generic check list with a one-line "no manifest for family
  X — falling back to generic checks" hint.  Adding a manifest is
  a 30-line YAML PR with no code changes.

- **[Risk]** Tool metadata (`install_docs.linux` URLs) rots when
  vendors restructure their docs site.
  → **Mitigation**: a CI link-checker (light, just HEAD requests)
  in `scripts/check_family_doc_links.py` runs on every manifest
  change.  Failures are warnings on the PR, not hard blockers,
  so a vendor URL flap doesn't block unrelated work.

- **[Risk]** `extends:` cycles or unknown parents make load
  pathological (infinite recursion, KeyError).
  → **Mitigation**: cycle detection during chain resolution
  raises `FamilyToolchainError(error_type="family-toolchain-cycle")`
  with the offending chain in the message; an unknown parent
  raises `family-toolchain-unknown-parent`.  Both are exercised
  by unit tests.

- **[Risk]** `core.diagnose.run` signature change breaks
  callers (TUI DoctorScreen, MCP tool).
  → **Mitigation**: `family` is a keyword-only parameter with a
  default of `None`.  Existing callers stay byte-identical until
  they opt in.

- **[Trade-off]** Wave 1 ships *no* installer, so users still see
  install hints to copy-paste.  Accepted: Wave 2 lands one PR
  later and the contract here is the bottleneck.  Without the
  manifest format, the installer has nothing to install *from*.

- **[Trade-off]** The `source` column adds a sixth column to a
  doctor table that already pushes terminal width on narrow
  shells.
  → **Mitigation**: Rich's `Table` already handles overflow with
  truncation; tests assert the column exists rather than its
  exact width.

## Migration Plan

This is purely additive.  No deprecations, no schema bumps to
user-facing files (`alloy.toml`), no data migrations.

Roll-out order (one PR per task block in `tasks.md`):

1. Land the schema + manifests + `toolchain_registry` module +
   tests.  No external surface change yet.
2. Land the `core.diagnose.run(family=...)` extension and the
   `--for` CLI flag.  Existing tests still pass; new tests
   cover the family-aware path.
3. Land the MCP `list_family_toolchain` tool.
4. Land the docs (`docs/TOOLCHAIN_REGISTRY.md`,
   `docs/ERROR_COOKBOOK.md` anchor) + the cheatsheet
   regeneration.

Rollback: each task block is independently revertable; the
manifests can ship without the doctor extension and vice versa
because both compile against today's `core.diagnose` API.

## Open Questions

- **Q1**: Should the `arm-cortex-m.yml` base also pin
  `arm-none-eabi-gdb` separately, or keep it implicit via the
  arm-gcc bundle?  Wave-2's installer will want to know which
  binaries the bundle ships *and* whether they appear on the
  capability map (gdb is the only one that maps to a `debug`
  capability — without it, `alloy debug` cannot run).
  → *Proposed answer*: declare `bundles: [arm-none-eabi-gdb,
  arm-none-eabi-size]` on the gcc requirement; the registry
  flattens bundles into a virtual capability set so
  `manifest.tool_for_capability("debug")` resolves correctly
  without a duplicate top-level entry.

- **Q2**: Where does `udev_required: true` get rendered today
  (Wave 1)?  We do not yet ship udev rules.
  → *Proposed answer*: render an `info`-severity row reminding
  Linux users they will need rules once they install the tool;
  Wave 2 owns the actual rule emission and `sudo` prompt.

- **Q3**: Do we want a per-board override (e.g., `nucleo_g071rb`
  has a built-in ST-Link, so probe-rs is *required* not
  *recommended*; same chip on a custom board with no probe is the
  opposite)?
  → *Deferred*: family-level granularity is enough for Wave 1.
  Per-board overrides land in a follow-up if the issue tracker
  shows users need them.
