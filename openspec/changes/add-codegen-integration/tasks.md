# Tasks — add-codegen-integration

## Phase 1: Discovery + entry-point shim

- [ ] 1.1 `core.codegen.discover_codegen_entry()` — `importlib`-based
      probe for `alloy_codegen.generate`.  Returns a typed
      `CodegenEntry { version, callable }` or `None`.
- [ ] 1.2 Soft-failure path: when the entry is missing, callers
      log a warning + skip; the build never crashes on a fresh
      machine that hasn't installed the codegen package.

## Phase 2: Stamp + cache invalidation

- [ ] 2.1 Stamp layout: `.alloy/generated/<device>/.stamp` is a
      JSON with `{"ir_sha": str, "codegen_version": str,
      "alloy_cli_version": str, "generated_at": str}`.
- [ ] 2.2 `core.codegen.regenerate_if_stale(config, layout) ->
      RegenResult` reads the stamp, compares to current values,
      runs codegen iff anything changed.
- [ ] 2.3 `core.codegen.force_regenerate` always runs.

## Phase 3: Build pipeline integration

- [ ] 3.1 `core.build.BuildResult` gains `codegen_returncode: int |
      None` and `codegen_skipped: bool`.
- [ ] 3.2 `core.build.run` calls `regenerate_if_stale` before
      cmake; failure surfaces as `codegen_returncode != 0` and
      blocks the cmake step.
- [ ] 3.3 `alloy build --regen` / `alloy build --no-codegen` flags.

## Phase 4: MCP tool

- [ ] 4.1 New tool `alloy.regenerate` wrapping
      `core.codegen.force_regenerate` — useful for LLMs that need
      to refresh generated headers between operations.
- [ ] 4.2 Tool descriptor lists side-effects: writes under
      `.alloy/generated/`.

## Phase 5: Tests

- [ ] 5.1 Stamp round-trip: stale stamp triggers regen, fresh
      stamp skips.
- [ ] 5.2 `discover_codegen_entry` returns `None` when the
      package is uninstallable; build still passes.
- [ ] 5.3 Mock alloy_codegen module emits one file under
      `.alloy/generated/include/` and updates the stamp.
- [ ] 5.4 MCP smoke for `alloy.regenerate`.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/build-pipeline/spec.md` (new
      capability) + an additive scenario in
      `specs/mcp-surface/spec.md`.
- [ ] 6.2 `openspec validate add-codegen-integration --strict`
      passes.
- [ ] 6.3 README "Quickstart" mentions that `alloy build` now
      regenerates headers automatically.
