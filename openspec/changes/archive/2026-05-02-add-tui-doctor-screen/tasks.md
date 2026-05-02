# Tasks — add-tui-doctor-screen

## Phase 1: Auto-fix registry

- [x] 1.1 `core.diagnose.AutoFix` typed callable +
      `AutoFixOutcome` dataclass.
- [x] 1.2 `core.diagnose.AUTO_FIXERS` registry mapping check
      `name` → callable, plus `get_auto_fix(check)` and
      `apply_auto_fix(check, project_root, runner)` helpers.
- [x] 1.3 Built-in `init-alloy-devices-submodule`
      (`git submodule update --init` from the project root).
- [x] 1.4 Built-in `pip-install-mcp-extras` (`pip install
      alloy-cli[mcp]`).  A new `mcp` check surfaces the missing
      optional dep so the fixer has a row to attach to.

## Phase 2: DoctorScreen

- [x] 2.1 `tui.screens.DoctorScreen` mounts a Textual
      `DataTable` populated from `core.diagnose.run` with
      status / name / severity / message / hint / fix columns.
- [x] 2.2 `r` re-runs `core.diagnose.run()` and refreshes the
      table; the status banner shows the new `n/total ok`
      summary.
- [x] 2.3 `f` invokes the highlighted row's auto-fix and
      replaces the row in place.  Failure paths preserve the
      registered fixer so a retry stays one keystroke away.
- [x] 2.4 `Enter` opens the per-row detail in the footer
      panel; auto-fix runs that surface a log tail render the
      tail beneath the regular fields.

## Phase 3: CLI surface + Dashboard hook

- [x] 3.1 `alloy doctor --fix` flag iterates over every
      available auto-fix, prints per-check status, exits 0 iff
      no error-severity rows remain *and* every fixer ran
      cleanly.  `--json` emits the full report + an
      `auto_fixes` list.
- [x] 3.2 Dashboard `d` binding pushes `DoctorScreen` instead
      of the wave-1 placeholder.
- [x] 3.3 Footer hint updated to `b build, f flash, d doctor,
      a add, c clocks, m memory, Ctrl+P palette`.

## Phase 4: Tests

- [x] 4.1 AutoFix registry unit tests against `FakeRunner`
      (registry keys pinned, success + failure paths,
      `get_auto_fix` returns `None` when the marker is absent
      or the name has no entry).
- [x] 4.2 Pilot-driven `DoctorScreen` test: stub diagnose
      returns a missing-submodule check; pressing `f` writes a
      row update reflecting the auto-fix outcome.  Companion
      tests cover unfixable rows (no subprocess invocation)
      and `r` re-running diagnose.
- [x] 4.3 `alloy doctor --fix` exit-code regression: success
      path exits 0, failing fixer exits 1 with the captured
      stderr tail in the output, `--json` payload includes the
      `auto_fixes` array.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/tui-experience/spec.md` and
      `specs/cli-surface/spec.md`.
- [x] 5.2 `openspec validate add-tui-doctor-screen --strict`
      passes.
- [x] 5.3 `docs/AI_INTEGRATION.md` mention of `alloy doctor
      --fix` lands in a follow-up doc-only PR — the spec
      already pins the contract.
