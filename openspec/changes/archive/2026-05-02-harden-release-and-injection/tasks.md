# Tasks — harden-release-and-injection

## Phase 1: Injection seam audit

- [x] 1.1 `tui.screens.dashboard` switched to
      `from alloy_cli.core import toolchain as _toolchain`;
      every `detect_*` call goes through the module attribute.
- [x] 1.2 No other module under `src/alloy_cli/` carries the
      direct-import pattern (verified via the new test).
- [x] 1.3 `tests/test_injection_seams.py` walks `src/alloy_cli/`
      and asserts no `from alloy_cli.core.toolchain import
      detect_*` lines survive.  Companion check ensures the
      dashboard module never re-exports module-local
      `detect_*` names.

## Phase 2: Single TOML emitter

- [x] 2.1 `core.project.dumps(config) -> str` is the canonical
      emitter; `core.project.write` is a thin wrapper.
- [x] 2.2 `core.peripherals._emit_toml` deleted; the `add_*`
      diff path consumes `core.project.dumps`.
- [x] 2.3 `core.clocks` and `mcp.tools` updated to import
      `dumps` instead of the private helper.
- [x] 2.4 Idempotence regression: `dumps → write → read →
      dumps` is byte-stable for both board-only and
      chip-only configurations.

## Phase 3: Public registry APIs

- [x] 3.1 `mcp.tools.ToolRegistry.get_tool(name)` raises
      `ToolError` when the name is missing; `pop_tool(name)`
      removes + returns or `None`.
- [x] 3.2 `tui.registry.ScreenRegistry.remove(name)` mirrors
      `pop_tool` for screen entries.
- [x] 3.3 `tests/test_mcp_server.py` and
      `tests/test_tui_foundation.py` migrated off `_tools` /
      `_entries`; the stdio server in `mcp/server.py` also
      uses the new public API.

## Phase 4: Release runbook + CHANGELOG

- [x] 4.1 `docs/RELEASING.md` covers tag → smoke → HIL →
      PyPI publish, plus the post-release CHANGELOG bump and
      self-hosted runner setup.
- [x] 4.2 `CHANGELOG.md` seeded with the wave-1 + wave-2
      proposals as the 0.1.0 bullet list; "Unreleased"
      section opened at the top.
- [x] 4.3 `.github/workflows/release.yml` runs a smoke step
      (`pip install dist/*.whl && alloy --version`) before the
      PyPI publish step; failure blocks the upload.

## Phase 5: HIL CI matrix

- [x] 5.1 `.github/workflows/hil.yml` runs on a self-hosted
      runner tagged `hil`; gated to `push: main` + PRs labelled
      `hil`.
- [x] 5.2 Pipeline: `alloy new` → `alloy build --profile
      debug` → assert ELF lands at the expected path.
- [x] 5.3 Runner-setup steps documented in
      `docs/RELEASING.md`.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/release-process/spec.md` (new
      capability) and `specs/peripheral-operations/spec.md`
      (the single-emitter contract).
- [x] 6.2 `openspec validate harden-release-and-injection
      --strict` passes.
- [x] 6.3 `docs/REVIEW.md` items 4 / 11 / 12 / 14 / 15 are
      crossed off in a follow-up doc-only PR — the spec
      already pins the contract.
