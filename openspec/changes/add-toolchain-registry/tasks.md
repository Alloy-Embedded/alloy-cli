## 1. Schema + manifest data

- [x] 1.1 Author `schema/family_toolchain_v1.json` (Draft 2020-12) with `additionalProperties: false` at every level, the closed `source` enum/pattern, the closed `capabilities` enum, and the conditional rule that `install_docs` is required when `source = "vendor"`.
- [x] 1.2 Add `tests/test_family_toolchain_schema.py` exercising the schema with a hand-rolled valid manifest and at least four negative fixtures (missing `schema_version`, unknown `source`, vendor without `install_docs`, unknown capability).
- [x] 1.3 Author `data/families/arm-cortex-m.yml` declaring `arm-none-eabi-gcc` (xpack), `cmake` (xpack), `ninja` (xpack), `probe-rs` (probe-rs-installer with `udev_required: true`).  Bundle `arm-none-eabi-gdb` and `arm-none-eabi-size` under the gcc requirement.
- [x] 1.4 Author `data/families/stm32f4.yml` (extends `arm-cortex-m`, core `cortex-m4f`, recommended `STM32CubeProgrammer` with vendor source + per-OS `install_docs`).
- [x] 1.5 Author `data/families/stm32g0.yml` (extends `arm-cortex-m`, core `cortex-m0plus`, recommended `STM32CubeProgrammer`).
- [x] 1.6 Author `data/families/rp2040.yml` (extends `arm-cortex-m`, core `cortex-m0plus`, required `picotool` from `github:raspberrypi/picotool` with capabilities `flash, reset`).
- [x] 1.7 Author `data/families/nrf52.yml` (extends `arm-cortex-m`, core `cortex-m4f`, recommended `nrfjprog` from vendor source with capabilities `recovery, flash`).
- [x] 1.8 Author `data/families/esp32.yml` (no extends, core `xtensa-lx6`, required `xtensa-esp-elf-gcc` from `espressif`, required `esptool` from `github:espressif/esptool` with capabilities `flash, reset, recovery`).
- [x] 1.9 Add `pyproject.toml` `shared-data` and `force-include` entries so `schema/family_toolchain_v1.json` and every `data/families/*.yml` ship inside the wheel under `alloy_cli/schema/` and `alloy_cli/data/families/`.

## 2. `core.toolchain_registry` module

- [x] 2.1 Add `FamilyToolchainError` (base) plus the four typed sub-classes (`family-toolchain-cycle`, `family-toolchain-unknown-parent`, `family-toolchain-schema`, `family-toolchain-not-found`) to `src/alloy_cli/core/errors.py`; export them from `__all__`.
- [x] 2.2 Add a unit test asserting every `error_type` string in the AlloyCliError hierarchy is unique (regression guard for the new types).
- [x] 2.3 Create `src/alloy_cli/core/toolchain_registry.py` with frozen+slots dataclasses `ToolRequirement` and `FamilyManifest`; enforce JSON-friendly field types only (str, int, bool, tuple of the above, dict[str, str] for `install_docs`).
- [x] 2.4 Implement `_load_schema()` mirroring `core.project._load_schema` (try repo path first, fall back to package data via `importlib.resources`).
- [x] 2.5 Implement `_locate_manifest(family_id)` with the same dual repo/package lookup.
- [x] 2.6 Implement `_parse_one(family_id)` that loads the YAML, validates against the schema, and returns the raw dict; raise `FamilyToolchainError(error_type="family-toolchain-schema")` on validation failure with the schema error path embedded in the message.
- [x] 2.7 Implement `_resolve_chain(family_id)` that walks `extends:` chains with cycle detection (track visited set, raise `family-toolchain-cycle` with the offending chain) and unknown-parent detection (raise `family-toolchain-unknown-parent`).
- [x] 2.8 Implement the merge step: child entries override base entries by `tool` name; arrays are flattened in order base→child→… and de-duplicated keeping the last occurrence.
- [x] 2.9 Implement `load_family(family_id) -> FamilyManifest` wiring the previous helpers, projecting the merged dict into the typed dataclasses.
- [x] 2.10 Implement on-disk cache under `<repo_root>/.alloy/cache/families/<family_id>.pkl` keyed on `(sha256(manifest_yaml) + sha256(parent_yaml...) + alloy_cli_version)`; mirror the eviction semantics of `core.ir._read_cached`.
- [x] 2.11 Implement `resolve_for_project(config: ProjectConfig) -> FamilyManifest | None` honouring the precedence in design D5 (`--for` is handled at the CLI layer; this function only sees the resolved family id).  Catch `FamilyToolchainError` from missing manifests and return `None` so doctor can fall back gracefully.
- [x] 2.12 Add `tool_for_capability(capability: str) -> ToolRequirement | None` helper on `FamilyManifest` that searches `required → recommended → optional` in that order; flatten the `bundles` list so a `debug` capability search returns `arm-none-eabi-gcc` when gdb is bundled there (per design Q1).
- [x] 2.13 Add `tests/core/test_toolchain_registry.py` covering: load each shipped manifest end-to-end, extends chain resolution, child overrides parent, cycle detection, unknown parent, capability lookup, cache hit on second call.

## 3. `core.diagnose` family-aware extension

- [x] 3.1 Add `source: str | None = None` to `CheckResult` (field default keeps existing call sites compatible).
- [x] 3.2 Add a `family: str | None = None` keyword-only parameter to `core.diagnose.run`.  When provided, attempt `toolchain_registry.load_family(family)`; on success build the check list from the manifest, on `FamilyToolchainError` fall back to the legacy generic list with an info-severity note.
- [x] 3.3 When `family` is None, call `toolchain_registry.resolve_for_project` to derive it from the project config; if that returns None, run the legacy generic check list (no behaviour change for users without a family-mapped target).
- [x] 3.4 Implement a per-tool detector dispatcher: tools whose `tool` name matches an existing `core.toolchain.detect_*` function reuse that detector; tools without an existing detector (e.g. `picotool`, `esptool`, `STM32CubeProgrammer`) get a generic `shutil.which`-based detector that surfaces `severity="info"` with the manifest's `install_docs` URL when missing AND `source == "vendor"`.
- [x] 3.5 For non-vendor missing tools without a dedicated detector, surface `severity="error"` with a placeholder install hint pointing at "Wave 2 will install via xpack" — the row should still render as red so users notice what's missing, but we do not yet pretend we can install it.
- [x] 3.6 Update the `DiagnosticReport.to_dict` JSON contract: bump `schema_version` to `"1.1"` and include the `source` field on every check entry (`null` for non-toolchain checks).
- [x] 3.7 Add `tests/core/test_diagnose_family.py` covering: doctor inside a stm32g0 project lists only stm32g0 tools; `family="esp32"` lists espressif tools; vendor-source missing renders as info, not error; unknown family falls back to generic with a note; `--json` output carries the new `source` field; legacy callers without `family=...` see byte-identical output.

## 4. `alloy doctor` CLI extension

- [x] 4.1 Add `--for <family_id>` Click option to `src/alloy_cli/commands/doctor.py`; validate the value against `toolchain_registry.known_families()` (helper to add in step 2.x — prefix-match the YAMLs at runtime).
- [x] 4.2 Pass the resolved family id (from `--for` or `resolve_for_project`) into `core.diagnose.run(family=...)`.
- [x] 4.3 Extend `_print_table` to render the `source` column; handle `None` as `-` so non-toolchain rows stay tidy.
- [x] 4.4 Update the `_run_fixes` path to skip vendor-source rows entirely (no auto-fix is registered, so today's `get_auto_fix(check) is None` guard covers it; assert it via a regression test rather than relying on incidental behaviour).
- [x] 4.5 Add a CLI integration test asserting `alloy doctor --for nonexistent` exits non-zero with the available family ids in stderr.
- [x] 4.6 Run `python scripts/generate_cheatsheet.py` so the new `--for` flag lands in `docs/CHEATSHEET.md`; verify CI's cheatsheet check passes.

## 5. MCP `list_family_toolchain` tool

- [x] 5.1 Add `_tool_list_family_toolchain` handler in `src/alloy_cli/mcp/tools.py` that calls `toolchain_registry.load_family` and projects the result to a JSON-friendly dict per the spec shape.
- [x] 5.2 Translate `FamilyToolchainError(error_type="family-toolchain-not-found")` into a `ToolError` envelope including `known_families: list[str]`.
- [x] 5.3 Register the tool in `_PARAM_SCHEMA` with `{"family_id": "string"}` and in `build_default_registry`'s handler dict.
- [x] 5.4 Add `tests/mcp/test_list_family_toolchain.py` covering: known family returns full manifest; unknown family returns the typed envelope with `known_families`; the tool appears in `registry.names()`.

## 6. Documentation + cookbook

- [x] 6.1 Author `docs/TOOLCHAIN_REGISTRY.md` covering: purpose vs IR, schema vocabulary with one example per field, the `extends:` walkthrough using `arm-cortex-m → stm32f4`, the `source` enum semantics, the "add a new family" walkthrough.
- [x] 6.2 Add anchors to `docs/ERROR_COOKBOOK.md` for the four new `family-toolchain-*` error types (trigger, example message, fix, related MCP tool).
- [x] 6.3 Add `tests/docs/test_toolchain_registry_doc.py` enforcing the doc covers every required schema field (regression guard for D-Q1 / D-Q2 ambiguity).
- [x] 6.4 Add a CI step to `scripts/check_family_doc_links.py` that performs HEAD requests against every `install_docs.*` URL in shipped manifests; failures are CI warnings (not blockers) so vendor URL flaps don't gate merges.

## 7. Validation + ship-readiness

- [x] 7.1 Run `openspec validate add-toolchain-registry --strict` and resolve every reported issue.
- [x] 7.2 Run `pytest -q tests/core/test_toolchain_registry.py tests/core/test_diagnose_family.py tests/mcp/test_list_family_toolchain.py` locally and confirm green.
- [x] 7.3 Run `ruff check src tests` and `pyright` — fix any new findings introduced by this change.
- [x] 7.4 Update `CHANGELOG.md` under `[Unreleased]` with a Wave-1 entry naming the new capability and the `--for` flag.
- [ ] 7.5 Open the PR titled `Implement add-toolchain-registry (Wave 1 of toolchain-management)` referencing this OpenSpec change in the description.
