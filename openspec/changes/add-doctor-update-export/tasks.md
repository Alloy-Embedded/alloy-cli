# Tasks — add-doctor-update-export

## Phase 1: alloy doctor

- [ ] 1.1 `core.diagnose.run() -> DiagnosticReport` aggregating
      Python / toolchain / probe / project / network /
      alloy-version checks.
- [ ] 1.2 `cli.doctor` prints the report (Rich table by default,
      `--json` for scripting).
- [ ] 1.3 `tui.screens.DoctorScreen` per `docs/TUI_DESIGN.md`
      Screen 11.  `r` re-run, `f` auto-fix safe issues.
- [ ] 1.4 Auto-fix: pip-install missing Python deps,
      `git submodule update --init` for alloy-devices-yml.

## Phase 2: alloy update

- [ ] 2.1 `core.update.resolve_upgrades(config, locks) -> tuple[Upgrade, ...]`.
- [ ] 2.2 `cli.update` Click command with `--dry-run` and
      `--frozen` flags.
- [ ] 2.3 Per-component upgraders:
      - alloy: download new SDK release + update `.alloy/version.lock`.
      - alloy-codegen: pip-upgrade.
      - alloy-devices-yml: `git submodule update --remote`.
      - alloy-cli: pip-upgrade with restart suggestion.
- [ ] 2.4 Atomic: writes new lockfile only after every component
      upgrade succeeds.

## Phase 3: alloy export

- [ ] 3.1 `core.export.ci.github(config) -> str` — GitHub Actions
      workflow YAML.
- [ ] 3.2 `core.export.ci.gitlab(config) -> str` — GitLab CI
      YAML.
- [ ] 3.3 `core.export.vscode.launch_json(config) -> dict` —
      cortex-debug + probe-rs.
- [ ] 3.4 `core.export.vscode.tasks_json(config) -> dict` —
      build / flash / debug.
- [ ] 3.5 `core.export.vscode.c_cpp_properties(config) -> dict` —
      include paths from generated headers.
- [ ] 3.6 `core.export.gdb(config) -> str` — `.gdbinit`.
- [ ] 3.7 `core.export.bom(config) -> dict` — chip + declared
      external components from `alloy.toml`.
- [ ] 3.8 `cli.export` Click command group with subcommand per
      kind.

## Phase 4: TUI advanced views

- [ ] 4.1 `tui.widgets.DmaMatrixWidget` —
      peripheral × channel grid.  Highlights conflicts.  Bind /
      unbind via `Enter`.
- [ ] 4.2 `tui.screens.DmaMatrixScreen` mounting the widget.
- [ ] 4.3 `tui.widgets.MemoryMapWidget` — stacked-bar + section
      list.  Driven by IR `memories[]` + last `.elf` map file.
- [ ] 4.4 `tui.screens.MemoryMapScreen` mounting the widget.
- [ ] 4.5 Snapshot tests for both screens.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/cli-surface/spec.md`,
      `specs/tui-experience/spec.md`.
- [ ] 5.2 `openspec validate add-doctor-update-export --strict`
      passes.
- [ ] 5.3 README "Daily driver" section updated with the new
      commands.
- [ ] 5.4 End-to-end smoke: `alloy new` → `alloy export vscode`
      → open in VS Code → `tasks.json` works.
