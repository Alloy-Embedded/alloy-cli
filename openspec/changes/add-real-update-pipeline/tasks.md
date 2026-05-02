# Tasks — add-real-update-pipeline

## Phase 1: Upgrader registry

- [ ] 1.1 `core.update.ComponentUpgrader` typed callable +
      `UpgradeContext` (project_dir, runner, current_lock).
- [ ] 1.2 `core.update.UPGRADERS` registry mapping component →
      upgrader callable.
- [ ] 1.3 `core.update.UpgradeOutcome { ok, log, restart_required }`
      dataclass.

## Phase 2: pip upgrader

- [ ] 2.1 `pip_upgrader(package_name)` factory — runs
      `python -m pip install --upgrade <name>==<target>` via the
      shared `core.process.runner`.
- [ ] 2.2 `pip_upgrader_with_restart` variant flips
      `restart_required=True` on success.

## Phase 3: git submodule upgrader

- [ ] 3.1 `git_submodule_upgrader` runs
      `git fetch --tags origin && git checkout <tag-or-sha>` in
      `data/devices/`.
- [ ] 3.2 Tag → SHA resolution: `git rev-list -n 1 v<version>`
      via the runner.
- [ ] 3.3 Surfaces "submodule not initialised" cleanly with a
      pointer to `git submodule update --init`.

## Phase 4: Atomic apply

- [ ] 4.1 `apply_upgrades` runs upgraders in dependency order
      (alloy-devices-yml → alloy-codegen → alloy → alloy-cli).
- [ ] 4.2 Any failure aborts before lockfile rewrite.
- [ ] 4.3 The CLI prints a per-component status line + the
      restart-required reminder for alloy-cli.

## Phase 5: Tests

- [ ] 5.1 FakeRunner-driven happy paths for each upgrader
      (covers pip + git plumbing).
- [ ] 5.2 Failure mid-sequence: alloy-codegen pip exits 1; the
      lockfile bytes do not change.
- [ ] 5.3 `--frozen` still refuses any change (regression).
- [ ] 5.4 `restart_required=True` surfaces a one-line
      notification.

## Phase 6: CI guardrail

- [ ] 6.1 `.github/workflows/update-smoke.yml` runs
      `alloy update --dry-run` on every PR.
- [ ] 6.2 Bot-friendly summary line: prints the number of pending
      upgrades; passes when all components are up to date.

## Phase 7: Spec + final checks

- [ ] 7.1 Spec deltas in `specs/cli-surface/spec.md`.
- [ ] 7.2 `openspec validate add-real-update-pipeline --strict`
      passes.
- [ ] 7.3 README "Daily-driver helpers" expands the alloy update
      example to mention atomic semantics.
