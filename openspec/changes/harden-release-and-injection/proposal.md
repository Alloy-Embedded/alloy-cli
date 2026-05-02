# Harden Release Process + Injection Seams

## Why

The post-launch review (`docs/REVIEW.md`) flagged three
engineering-hygiene items that compound when ignored:

1. **Direct-import bindings block injection.**  Several modules
   do `from alloy_cli.core.toolchain import detect_arm_gcc, ...`
   instead of `from alloy_cli.core import toolchain as
   _toolchain`.  Tests + the screenshot generator have to
   monkey-patch every importer's local copy of the binding to
   stub a single function.  We caught this for `core.flash` and
   `core.build` already; `tui.screens.dashboard` still has it.
2. **Duplicated TOML emission.**  `core.peripherals._emit_toml`
   mirrors `core.project.write` byte-for-byte using the
   now-public `emit_section` / `emit_peripheral` helpers.
   Two emitters drift; we need one.
3. **Private-attribute access in tests.**  Tests reach into
   `registry._tools` (MCP) and `global_registry._entries`
   (TUI registry) because the public API is incomplete.
4. **No CHANGELOG / release process.**  Hatch-vcs gives us
   versions; we don't yet have a release runbook, a CHANGELOG,
   or hardware-in-the-loop CI matrix to gate releases.

This proposal takes one swing at all four.

## What Changes

### Injection seams

- Replace every `from alloy_cli.core.toolchain import detect_*`
  + similar bindings with `from alloy_cli.core import
  toolchain as _toolchain`; the call sites become
  `_toolchain.detect_arm_gcc()`.  Affected modules: `tui.screens.
  dashboard`, anything else that landed pre-#13 with the same
  pattern.
- Add a regression lint: `pytest tests/test_injection_seams.py`
  walks the source tree and flags new `from alloy_cli.core.X
  import detect_*` lines.

### Single TOML emitter

- Move every emitter into `core.project.dumps(config) -> str`.
- `core.project.write` calls `dumps`.
- `core.peripherals._emit_toml` is deleted; the diff path
  consumes `dumps`.
- Idempotence test: dumps(read(write(dumps(config)))) is
  byte-stable.

### Public registry APIs

- `tools.ToolRegistry` gets `get_tool(name) -> Tool` and
  `pop_tool(name) -> Tool | None`.
- `tui.registry.ScreenRegistry` mirrors with `get` (already
  exists) + `remove(name) -> None`.
- Tests stop reaching into `_tools` / `_entries`.

### Release runbook

- `docs/RELEASING.md` walks through: `git tag`, `gh release
  create`, PyPI trusted-publishing flow, post-release version
  bump, CHANGELOG entry.
- `CHANGELOG.md` seeded with the 15 archived proposals as the
  0.1.0 bullet list.
- `.github/workflows/release.yml` already exists; this proposal
  documents + tests it (dry-run via `pip install dist/*.whl`
  inside the workflow before the publish step).

### Hardware-in-the-loop CI matrix

- `.github/workflows/hil.yml` runs on a self-hosted runner with
  `arm-none-eabi-gcc` + `probe-rs` installed.  Triggered by
  pushes to `main` only.
- The job: `alloy new firmware --board nucleo_g071rb` →
  `alloy build` → assert `firmware.elf` exists.
- Initially gated to one board; the matrix expands as the
  runner pool grows.

## Impact

- **Test ergonomics**: stubbing toolchain detection becomes a
  one-liner monkey-patch instead of patching three modules.
- **Refactor safety**: the dedup'd TOML emitter is the single
  source of truth — no risk of the diff path drifting from
  `core.project.write`.
- **Release confidence**: the runbook + HIL gate mean we never
  push a release that can't actually build a real binary.
- **Public API stability**: tests stop coupling to private
  attributes; refactors don't crash the suite.

## What this DOES NOT do

- Does not change the public CLI surface.
- Does not introduce a plugin system (deferred).
- Does not bring up multi-board HIL coverage at first launch
  (start with one board, expand later).
- Does not enforce semver-strictness on the version bump
  process — convention only.
