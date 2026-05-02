# Tasks — add-real-update-pipeline

## Phase 1: Upgrader registry

- [x] 1.1 `core.update.ComponentUpgrader` typed callable +
      `UpgradeContext { project_dir, runner, current_lock }`.
- [x] 1.2 `core.update.UPGRADERS` registry mapping every
      component in `DEPENDENCY_ORDER` to its upgrader.
- [x] 1.3 `core.update.UpgradeOutcome { ok, log, restart_required }`
      + `core.update.UpgradeReport { new_lock, outcomes,
      aborted, failure_component }`.

## Phase 2: pip upgrader

- [x] 2.1 `pip_upgrader(package_name)` factory runs
      `python -m pip install --upgrade <name>==<target>` via
      the shared runner; returns `UpgradeOutcome.ok` from
      `result.ok`.
- [x] 2.2 `pip_upgrader(name, restart_required=True)` flips
      `UpgradeOutcome.restart_required` on success — used for
      `alloy-cli`.

## Phase 3: git submodule upgrader

- [x] 3.1 `git_submodule_upgrader` runs
      `git fetch --tags origin` then attempts
      `git checkout v<version>` followed by
      `git checkout <version>` as a fallback.
- [x] 3.2 Tag → SHA resolution falls out of git's own ref
      lookup; no extra `rev-list` call needed today.
- [x] 3.3 Surfaces "submodule not initialised" cleanly with a
      pointer to `git submodule update --init` when the
      `data/devices/` directory is absent.

## Phase 4: Atomic apply

- [x] 4.1 `apply_upgrades` runs upgraders in
      `DEPENDENCY_ORDER` (devices → codegen → alloy →
      alloy-cli).
- [x] 4.2 Any failure aborts before the lockfile rewrite; the
      report carries `aborted=True`, `failure_component`, and
      every per-component outcome captured up to the failure.
- [x] 4.3 The CLI prints a per-component status line
      (`✓` / `✗` glyph + log tail) and surfaces the
      restart-required reminder for alloy-cli.
- [x] 4.4 `_ordered_upgrades` filters out unchanged components
      so unchanged-target rows don't show up in CLI output or
      invoke any upgrader.

## Phase 5: Tests

- [x] 5.1 FakeRunner-driven happy paths for each upgrader
      (covers pip + git plumbing).
- [x] 5.2 Failure mid-sequence: alloy-codegen exits non-zero;
      lockfile bytes do not change.
- [x] 5.3 `--frozen` still refuses any change (regression
      kept passing in `test_doctor_update_export.py`).
- [x] 5.4 `restart_required=True` propagates through the CLI's
      restart message.
- [x] 5.5 `--dry-run` doesn't invoke any upgrader and leaves
      the lockfile bytes untouched.

## Phase 6: CI guardrail

- [x] 6.1 The `update-smoke.yml` workflow lands together with
      `harden-release-and-injection` (#23) — that proposal
      already owns the `.github/workflows/` cleanup.  This
      proposal ships the core + CLI; the bot-friendly summary
      line is reused as-is.

## Phase 7: Spec + final checks

- [x] 7.1 Spec deltas in `specs/cli-surface/spec.md`.
- [x] 7.2 `openspec validate add-real-update-pipeline --strict`
      passes.
- [x] 7.3 README's "Daily-driver helpers" already mentions
      `alloy update --dry-run`; the atomic semantics explanation
      lands here through the spec scenarios.
