# Tasks — add-tui-doctor-screen

## Phase 1: Auto-fix registry

- [ ] 1.1 `core.diagnose.AutoFix` typed callable +
      `AutoFixOutcome` dataclass.
- [ ] 1.2 `core.diagnose.AUTO_FIXERS` registry mapping check
      `name` → callable.
- [ ] 1.3 Built-in `init-alloy-devices-submodule`.
- [ ] 1.4 Built-in `pip-install-mcp-extras` (covers
      `pip install alloy-cli[mcp]`).

## Phase 2: DoctorScreen

- [ ] 2.1 `tui.screens.DoctorScreen` mounts a Textual `DataTable`
      with the full report.
- [ ] 2.2 `r` re-runs `core.diagnose.run()` and refreshes the
      table.
- [ ] 2.3 `f` invokes the highlighted row's auto-fix; updates the
      row in place with the new outcome.
- [ ] 2.4 `Enter` opens the per-row detail in a side panel.

## Phase 3: CLI surface + Dashboard hook

- [ ] 3.1 `alloy doctor --fix` flag iterates over every available
      auto-fix; prints per-check status; exits 0 iff no
      error-severity rows remain.
- [ ] 3.2 Dashboard `d` binding pushes `DoctorScreen` instead of
      the existing no-op.
- [ ] 3.3 Footer hint "press d to open Doctor".

## Phase 4: Tests

- [ ] 4.1 AutoFix registry unit tests against FakeRunner.
- [ ] 4.2 Pilot-driven DoctorScreen test: mocked diagnose returns
      a missing-submodule check; pressing `f` writes a row update
      reflecting the auto-fix outcome.
- [ ] 4.3 `alloy doctor --fix` exit-code regression for both
      success + failure paths.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/tui-experience/spec.md` and
      `specs/cli-surface/spec.md`.
- [ ] 5.2 `openspec validate add-tui-doctor-screen --strict` passes.
- [ ] 5.3 `docs/AI_INTEGRATION.md` mentions `alloy doctor --fix`
      as the recommended container warm-up step.
