## 1. Shared install orchestrator (UI-free)

- [x] 1.1 Add `OnboardingCancelledError` to `src/alloy_cli/core/errors.py` (subclass of `AlloyCliError`, `error_type="onboarding-cancelled"`); export from `__all__`; extend the uniqueness regression test.
- [x] 1.2 Add the `onboarding-cancelled` anchor to `docs/ERROR_COOKBOOK.md` so `scripts/check_error_cookbook.py` stays green.
- [x] 1.3 Create `src/alloy_cli/core/toolchain_orchestrator.py` with frozen+slots dataclasses `InstallEvent` (sealed union of `ToolStarted`, `ToolSkippedVendor`, `ToolSkippedHostUnsupported`, `ToolDownloaded`, `ToolInstalled`, `ToolFailed`), `InstallOutcome` (one row per tool), and `InstallReport` (`outcomes`, `lockfile_updated`, `total_bytes_downloaded`, `host`).
- [x] 1.4 Implement `install_family(manifest, *, project_root=None, include_optional=False, force=False, on_event=None, downloader=None)` walking the family's required + recommended (+ optional?) tiers, dispatching every non-vendor entry through `_ts.adapter_for(...)` + `_tm.install(...)`, updating `.alloy/toolchain.lock` (when project_root is set), and returning the typed `InstallReport`.  Vendor tools short-circuit with the per-OS install_doc URL; failures from one tool do NOT abort the rest.
- [x] 1.5 Add `tests/test_toolchain_orchestrator.py` with at least: every shipped family's required tier walks cleanly with a FakeDownloader; vendor short-circuit (no downloader call, install_doc_url populated); host-unsupported short-circuit; per-tool failure does not abort the rest; lockfile written when project_root is set, NOT written when None; idempotent re-run; on_event callbacks fire in order (started → downloaded → installed) per tool.
- [x] 1.6 Add `tests/test_toolchain_onboarding_contract.py` enforcing the "every entry point routes through the orchestrator" rule via AST scan: `commands/new.py`, `commands/setup.py`, `tui/screens/onboarding.py`, and the new MCP handler MUST NOT contain a direct call to `tool_sources.adapter_for` or `toolchain_manager.install`.

## 2. `alloy new` post-scaffold prompt

- [x] 2.1 Refactor `commands/new.py` to dispatch the install through `toolchain_orchestrator.install_family` after `scaffold(...)` returns.  Add `--install-toolchain` / `--no-install-toolchain` Click flags and an `--auto` flag that suppresses every interactive confirmation.
- [x] 2.2 Implement `_should_offer_install(install_flag, tty)` matching design D3: explicit flag wins; default Y in TTY, default N otherwise.  Pin it via a unit test that exercises every (flag, tty) combination.
- [x] 2.3 Print the install plan (Rich table) before the prompt so the user knows what they're saying Y/N to.  Use `_plan_for_family` helper from `commands/toolchain.py` (refactor to a shared helper if necessary, or expose it via `toolchain_orchestrator`).
- [x] 2.4 Always print the next-step command at the end of the run — even when the install was skipped.  When skipped, the message names `alloy toolchain install` explicitly.
- [x] 2.5 Wire `OnboardingCancelledError` to exit code 130 in the CLI wrapper; the partial outcomes get summarised before exit.
- [x] 2.6 Update `tests/test_command_new.py` (existing) with new tests: `--install-toolchain --auto` writes the lockfile + populates the store; `--no-install-toolchain` writes nothing; TTY default with simulated `Y` proceeds; TTY default with simulated `n` skips; non-TTY without flag skips; the install plan prints before the prompt.

## 3. `alloy doctor --fix` toolchain extension

- [x] 3.1 Extend `core/diagnose.py` to register synthetic check names (`toolchain:<tool-name>`) for every missing non-vendor tool the resolved family declares.  Each check carries an `auto_fix` string + appears under a new `_print_table` row.
- [x] 3.2 Register a new `AUTO_FIXERS` entry that dispatches a single tool through `toolchain_orchestrator.install_family` (`include_optional=False`, `force=False`).  The entry maps the synthetic check name to a fixer callable that resolves the family from `project_dir`, builds a single-tool slice of the manifest, and runs the orchestrator.
- [x] 3.3 Add a `--with-recommended` flag to `commands/doctor.py` so `--fix` extends to the recommended tier when set.  Default is required-only.
- [x] 3.4 Update `_run_fixes` (existing) so per-fixer failures are captured and surfaced in `_print_fix_summary` without aborting the rest of the queue.  Existing tests already assert this for the legacy fixers; Wave 3 just preserves the contract.
- [x] 3.5 Update `tests/test_doctor_for_flag.py` (existing) + `tests/test_doctor_update_export.py` (existing) with new tests: `--fix` in stm32g0 with empty store installs all four required tools in sequence; vendor tools render as info, never attempted; per-tool failure surfaces typed in the summary; `--with-recommended` extends the queue to the recommended tier.

## 4. `alloy setup` standalone command

- [x] 4.1 Create `src/alloy_cli/commands/setup.py` with the Click command + flags (`--board`, `--family`, `--auto`, `--no-tui`, `--project-dir`).
- [x] 4.2 Implement the project-state detection: present project + resolved family → install path; missing project → embed the `alloy new` flow first; half-installed (lockfile pins something missing from the store) → run install to repair.
- [x] 4.3 Implement the family picker: outside a project, render a curated list from `boards.load_catalog()` sorted by tier; user selects one.  When `--no-tui` is set OR STDIN is non-TTY, fall back to a numbered line-based prompt.
- [ ] 4.4 When STDIN is a TTY and `--no-tui` is NOT set, hand off to the TUI `OnboardingScreen` (block 5) instead of the line-based wizard.   *(deferred to Wave 3 group 5; see TODO in setup.py)*
- [x] 4.5 Wire SIGINT to raise `OnboardingCancelledError` cleanly; CLI exits 130 with a partial-progress summary.
- [x] 4.6 Print the canonical "next steps" panel after every successful run (`alloy build`, `alloy flash`, `alloy ui`).
- [x] 4.7 Register `setup_command` in `src/alloy_cli/main.py`.
- [x] 4.8 Run `python scripts/generate_cheatsheet.py` so the new verb lands in `docs/CHEATSHEET.md`.
- [x] 4.9 Add `tests/test_command_setup.py`: setup outside a project + `--auto` + `--board nucleo_g071rb` scaffolds and installs; setup inside a project + `--auto` skips scaffolding; `--no-tui` forces line prompts; `--auto` never blocks on STDIN; SIGINT exits 130 with partial progress.

## 5. TUI `OnboardingScreen` real wizard

- [ ] 5.1 Replace the Wave-1 placeholder in `src/alloy_cli/tui/screens/onboarding.py` with the three-phase wizard: family picker → plan review → live progress.
- [ ] 5.2 Add an `InstallProgressWidget` (Textual `Container` + `ProgressBar`) under `src/alloy_cli/tui/widgets/install_progress.py`.  One row per tool; subscribes to `InstallEvent` messages.
- [ ] 5.3 Implement worker-thread dispatch: the screen spawns the orchestrator on a worker, pumps events into a Textual message queue, updates widgets reactively.  Cancellation from the screen raises `OnboardingCancelledError` from the calling context.
- [ ] 5.4 Add a final "All set" panel rendering the next-step commands the CLI also prints.  Include an `[Exit wizard]` button that pops the screen.
- [ ] 5.5 Register the screen via `register_screen("onboarding", title="Onboarding", ...)` so the command palette discovers it.
- [ ] 5.6 Add SVG snapshot tests for each phase (`tests/snapshots/onboarding-{family-picker,plan-review,progress,done}.svg`).
- [ ] 5.7 Add `tests/test_onboarding_screen.py` (Textual-snapshot fixture): family picker auto-completes inside a project; clicking Install spawns the orchestrator; vendor row stays dim with install_doc URL; cancellation raises the typed error.

## 6. MCP `toolchain_apply_install_plan`

- [ ] 6.1 Add `_tool_toolchain_apply_install_plan(registry, *, family_id)` handler in `src/alloy_cli/mcp/tools.py` that dispatches through `toolchain_orchestrator.install_family` and projects every outcome to the JSON shape from spec D7.
- [ ] 6.2 Idempotency contract: a re-run on a fully-installed family returns every outcome with `skipped=true, reason="already-installed"` and `total_bytes_downloaded=0`.
- [ ] 6.3 Vendor tools surface with `skipped=true, reason="vendor"` and `install_doc_url` populated.  Error envelopes propagate Wave-2's typed error_types unchanged.
- [ ] 6.4 Register the tool in `_PARAM_SCHEMA` (`{"family_id": "string"}`) and in `build_default_registry`'s handler dict.
- [ ] 6.5 Update `src/alloy_cli/integrations/opencode/system_prompt.md` to document the two-phase contract (preview via `toolchain_install_plan`, apply via `toolchain_apply_install_plan`, after explicit human confirmation).
- [ ] 6.6 Add `tests/test_mcp_toolchain_apply.py` covering: full install populates outcomes + lockfile_updated; re-run is idempotent + zero bytes; vendor surfaces reason="vendor" + install_doc_url; tool failure surfaces typed error_type per row without aborting; tool list discovery includes the new entry.

## 7. Documentation

- [ ] 7.1 Author `docs/TOOLCHAIN_ONBOARDING.md` covering the four entry points + decision matrix + orchestrator API + InstallEvent contract + two-phase MCP pattern + cancellation contract + cross-links to Waves 1-2 docs.
- [ ] 7.2 Rewrite `docs/QUICKSTART.md` to use the post-scaffold install prompt as the canonical "five minutes to first ELF" path; reference `--no-install-toolchain` as the escape hatch and `alloy doctor --fix` as the "existing project" command.
- [ ] 7.3 Add `tests/test_toolchain_onboarding_doc.py` mirroring Wave 1 + Wave 2 doc tests: every `InstallEvent` class is namedropped, every entry point has a subsection, every cookbook anchor for relevant errors is linked, the cancellation contract is documented.
- [ ] 7.4 Run `python scripts/generate_cheatsheet.py` and verify the new `alloy setup` + the modified `alloy new` flags land.

## 8. Validation + ship-readiness

- [ ] 8.1 Run `openspec validate add-onboarding-wizard --strict` and resolve every reported issue.
- [ ] 8.2 Run targeted test files locally and confirm green: `pytest tests/test_toolchain_orchestrator.py tests/test_toolchain_onboarding_contract.py tests/test_command_setup.py tests/test_onboarding_screen.py tests/test_mcp_toolchain_apply.py tests/test_toolchain_onboarding_doc.py`.
- [ ] 8.3 Run `pytest -q --deselect tests/test_mcp_server.py::test_alloy_mcp_serve_stdio_round_trips_via_subprocess` and confirm green.
- [ ] 8.4 Run `ruff check src tests scripts` and `pyright src/alloy_cli` — fix any new findings introduced by this change.
- [ ] 8.5 Update `CHANGELOG.md` under `[Unreleased]` with a Wave-3 entry naming the new capability, the `alloy setup` verb, the `--install-toolchain` flags on `alloy new`, the `--with-recommended` flag on `alloy doctor`, the TUI `OnboardingScreen`, and the new MCP write tool.
- [ ] 8.6 Open the PR titled `Implement add-onboarding-wizard (Wave 3 of toolchain-management)` referencing this OpenSpec change in the description.
