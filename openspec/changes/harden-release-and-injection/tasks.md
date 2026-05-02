# Tasks — harden-release-and-injection

## Phase 1: Injection seam audit

- [ ] 1.1 Replace `from alloy_cli.core.toolchain import detect_*`
      with the module-import pattern in every module that has
      it (start with `tui.screens.dashboard`).
- [ ] 1.2 Same audit for any other `core.X` module that's
      monkey-patched in tests.
- [ ] 1.3 `tests/test_injection_seams.py` walks `src/` and asserts
      no module-level `detect_*` direct imports survive.

## Phase 2: Single TOML emitter

- [ ] 2.1 `core.project.dumps(config) -> str`.
- [ ] 2.2 `core.project.write` calls `dumps`.
- [ ] 2.3 Delete `core.peripherals._emit_toml`; redirect callers
      to `core.project.dumps`.
- [ ] 2.4 Idempotence test:
      `read(write_to_temp(dumps(config))) == config` byte-for-byte.

## Phase 3: Public registry APIs

- [ ] 3.1 `tools.ToolRegistry.get_tool(name)` +
      `pop_tool(name)`.
- [ ] 3.2 `tui.registry.ScreenRegistry.remove(name)`.
- [ ] 3.3 Migrate every test that accessed `_tools` / `_entries`
      to the public API.

## Phase 4: Release runbook + CHANGELOG

- [ ] 4.1 `docs/RELEASING.md` covers tag / gh release / PyPI
      trusted-publishing / post-release bump.
- [ ] 4.2 `CHANGELOG.md` seeded with the 15 archived proposals
      as the 0.1.0 bullet list.
- [ ] 4.3 `.github/workflows/release.yml` augmented with a
      pre-publish smoke step:
      `pip install dist/*.whl && alloy --version`.

## Phase 5: HIL CI matrix

- [ ] 5.1 `.github/workflows/hil.yml` runs on a self-hosted
      runner; gated on `main` pushes.
- [ ] 5.2 Pipeline: scaffold + build the nucleo_g071rb fixture;
      assert the ELF lands at the expected path.
- [ ] 5.3 Document the runner-setup steps in
      `docs/RELEASING.md`.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/release-process/spec.md` (new
      capability) and `specs/peripheral-operations/spec.md` (the
      single-emitter contract).
- [ ] 6.2 `openspec validate harden-release-and-injection
      --strict` passes.
- [ ] 6.3 `docs/REVIEW.md` items 4 / 11 / 12 / 14 / 15 are
      crossed off after this change archives.
