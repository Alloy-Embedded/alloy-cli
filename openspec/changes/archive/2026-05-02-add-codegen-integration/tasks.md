# Tasks — add-codegen-integration

## Phase 1: Discovery + entry-point shim

- [x] 1.1 `core.codegen.discover_codegen_entry()` —
      `importlib.import_module("alloy_codegen")` probe; returns a
      typed `CodegenEntry { version, callable }` or `None`.
- [x] 1.2 Soft-failure: missing module → debug log + return
      `None`; missing `generate` callable → warning log + return
      `None`.  Build pipeline keeps going with
      `codegen_returncode=None`.

## Phase 2: Stamp + cache invalidation

- [x] 2.1 `.alloy/generated/<device>/.stamp` is a JSON document
      with `ir_sha`, `codegen_version`, `alloy_cli_version`,
      `generated_at` — emitted by `_Stamp.to_json` /
      `_Stamp.from_json`.
- [x] 2.2 `core.codegen.regenerate_if_stale(config, layout, *,
      entry=None, on_line=None)` reads the stamp, compares
      against `_expected_stamp`, runs codegen iff anything
      differs.
- [x] 2.3 `core.codegen.force_regenerate(...)` always runs;
      raises `CodegenError` when alloy-codegen is uninstalled
      and the caller asked for an explicit run.

## Phase 3: Build pipeline integration

- [x] 3.1 `BuildResult` gained `codegen_returncode: int | None`,
      `codegen_skipped: bool`, and `codegen_reason: str` so the
      CLI / TUI / MCP surfaces can display the new step.
- [x] 3.2 `core.build.run` now runs `regenerate_if_stale` before
      cmake.  A non-zero codegen rc returns a build result with
      cmake/build rc=-1; a zero rc proceeds to the cmake +
      ninja phases.
- [x] 3.3 `alloy build --regen` flips `regen=True`;
      `alloy build --no-codegen` flips `skip_codegen=True`.
      The status line in the CLI reports whether codegen ran,
      was skipped (with a reason), or wasn't installed.

## Phase 4: MCP tool

- [x] 4.1 `alloy.regenerate` MCP tool wrapping
      `core.codegen.force_regenerate`; raises
      `ToolError(error_type="codegen-not-installed")` when the
      dep is missing.
- [x] 4.2 Tool description names the side effect (writes under
      `.alloy/generated/`); response carries the relative paths
      of every file written + the stamp's `reason` field.
- [x] 4.3 `alloy.build` tool now surfaces `codegen_returncode`,
      `codegen_skipped`, and `codegen_reason` so LLM clients can
      branch on a codegen-only failure.

## Phase 5: Tests

- [x] 5.1 `tests/test_codegen.py` (12 cases) covers stamp
      missing → run, stamp fresh → skip, version bump →
      re-run, skipped-with-reason when entry is None,
      exception-from-callable → returncode=1, force_regenerate
      ignoring fresh stamp, force_regenerate raising when not
      installed, board-only project label.
- [x] 5.2 `tests/test_build.py` gained 6 cases:
      missing-codegen → ok with returncode=None, present-entry
      runs once, second build hits the stamp cache, --regen
      forces a re-run, --no-codegen bypasses, codegen failure
      aborts before cmake.
- [x] 5.3 `tests/test_mcp_server.py` gained 4 cases for the new
      tool: registry shape, missing-codegen error, success
      writes files + stamp, build tool surfaces codegen rc.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/build-pipeline/spec.md` (new
      capability) + an additive scenario in
      `specs/mcp-surface/spec.md`.
- [x] 6.2 `openspec validate add-codegen-integration --strict`
      passes.
- [x] 6.3 README "Quickstart" already documents
      `alloy build` end-to-end; the new flags land in the same
      block when this proposal archives.
