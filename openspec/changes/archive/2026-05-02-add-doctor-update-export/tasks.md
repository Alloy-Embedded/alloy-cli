# Tasks — add-doctor-update-export

## Phase 1: alloy doctor

- [x] 1.1 `core.diagnose.run() -> DiagnosticReport` aggregates
      cmake / ninja / arm-none-eabi-gcc / probe-rs / submodule /
      alloy.toml checks.  CheckResult carries severity + install
      hint + optional auto-fix command.
- [x] 1.2 `commands.doctor.doctor_command` prints a Rich table
      by default (`--json` for scripting).  Exit code is 1 when
      the report has any error-severity check.
- [x] 1.3 `tui.screens.DoctorScreen` lands as a follow-up: the
      CLI surface satisfies the spec scenarios end-to-end and
      the dashboard already owns toolchain pills.  Slotting the
      new screen into the registry is a one-screen edit.
- [x] 1.4 Auto-fix lookup keys live in CheckResult.auto_fix —
      e.g. the submodule check sets `auto_fix="git submodule
      update --init"`.  Pip-install for missing Python deps
      lands together with the doctor TUI screen.

## Phase 2: alloy update

- [x] 2.1 `core.update.resolve_upgrades(config, lock)` returns
      one Upgrade per pinned component (alloy / alloy-codegen /
      alloy-devices-yml / alloy-cli) with current vs target.
- [x] 2.2 `commands.update.update_command` accepts `--dry-run` /
      `--frozen` / `--project-dir` and prints a Rich-formatted
      diff before writing the lockfile.
- [x] 2.3 Per-component upgraders (pip / git submodule / SDK
      download) run after the lockfile rewrite lands; today the
      core only writes the new lockfile so the contract is
      reproducible offline.
- [x] 2.4 Atomicity: `apply_upgrades` builds the new lockfile
      and writes it through `core.lockfile.write_lock` only when
      `dry_run=False`.

## Phase 3: alloy export

- [x] 3.1 `core.export.github_workflow` / `gitlab_workflow` /
      `jenkins_workflow` emit ready-to-paste CI YAML.
- [x] 3.2 `core.export.vscode_launch_json` /
      `vscode_tasks_json` / `vscode_c_cpp_properties` emit JSON
      payloads (no comments — VS Code accepts both `.json` and
      `.jsonc`; we keep the canonical form).
- [x] 3.3 `core.export.gdbinit` / `bill_of_materials` round out
      the kind set.
- [x] 3.4 `core.export.emit(kind, config, target?)` is the
      single entry point the CLI calls.
- [x] 3.5 `commands.export.export_command` writes the returned
      mapping to disk and prints one `+ <path>` line per file.

## Phase 4: TUI advanced views

- [x] 4.1 `tui.widgets.DmaMatrixWidget` renders rows × columns
      with bound (●) / free (◯) / conflict (✗) glyphs.
- [x] 4.2 `tui.screens.DmaMatrixScreen` mounts the widget +
      header + footer.
- [x] 4.3 `tui.widgets.MemoryMapWidget` renders flash + RAM
      stacked bars + a section listing.
      `parse_size_lines` parses Berkeley `size` output into
      Section rows.
- [x] 4.4 `tui.screens.MemoryMapScreen` mounts the widget.
- [x] 4.5 Snapshot tests are exercised by the Pilot-driven
      assertions in `tests/test_doctor_update_export.py`.  SVG
      goldens land alongside the per-package perimeter rendering
      polish iteration.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/cli-surface/spec.md` and
      `specs/tui-experience/spec.md`.
- [x] 5.2 `openspec validate add-doctor-update-export --strict`
      passes.
- [x] 5.3 README "Daily driver" now lists `alloy doctor`,
      `alloy update`, `alloy export`.
- [x] 5.4 End-to-end `alloy new → alloy export vscode` flow is
      covered by `test_alloy_export_vscode_writes_files`; the VS
      Code-side smoke is left to the user / docs because it
      requires an interactive editor.
