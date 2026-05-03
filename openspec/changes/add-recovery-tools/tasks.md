## 1. Shared probe orchestrator (UI-free)

- [ ] 1.1 Add nine new error classes to `src/alloy_cli/core/errors.py`: `FamilyToolchainProbeError` (base) + `FamilyToolchainProbeNotFoundError` / `*NotAttachedError` / `*MultipleAttachedError` / `*UnauthorisedError`, plus `FamilyToolchainEraseError` (base) + `*AbortedError` / `*UnsupportedRegionError` / `*ConfirmationRequiredError` / `*ProbeFailedError`, plus `ProbeOperationCancelledError` (carries `duration_ms`, `bytes_captured`, `last_line`).  Stable `error_type` strings.  Export from `__all__`.  Extend `tests/test_errors_uniqueness.py` so the suite enforces uniqueness + kebab-case.
- [ ] 1.2 Add cookbook anchors for every new `error_type` to `docs/ERROR_COOKBOOK.md` so `scripts/check_error_cookbook.py` stays green.
- [ ] 1.3 Create `src/alloy_cli/core/probe_orchestrator.py` with frozen+slots dataclasses: `ProbeIdentity` (vid/pid/serial/kind/vendor_only), `ResetReport`, `EraseRegion`, `ErasePlan`, `EraseReport`, and the sealed `MonitorEvent` union (`MonitorOpened`, `MonitorBytes`, `MonitorClosed`).  Plus `Probe` Protocol declaring `identity`, `reset`, `erase`, `monitor`.
- [ ] 1.4 Implement the public functions: `select_probe(*, hint, project_root)` (single-attached heuristic + `--probe` selector + multiple-attached error); `reset_target(probe, *, method, halt_after)`; `plan_erase(probe, *, regions, project_root)` (resolves IR aliases or `0xBASE-0xEND` ranges); `execute_erase(probe, plan)`; `open_monitor(probe, *, port, baud, mode, on_event)`.  Module is UI-free — no Click / Rich / Textual / `input()` / `sys.stdin`.
- [ ] 1.5 Implement `_RealProbeRsProbe` (subprocess wrapper around the lockfile-pinned `probe-rs` binary) and a `FakeProbe` test seam recording every call + emitting scripted `MonitorEvent`s.
- [ ] 1.6 Add `tests/test_probe_orchestrator.py` covering: `select_probe` matches `vid:pid:serial`; single-attached fast path; multiple-attached + no `--probe` raises `family-toolchain-probe-multiple-attached`; vendor-only probe raises `family-toolchain-probe-unauthorised`; `reset_target` returns a `ResetReport` with the right method; `plan_erase` resolves IR aliases + raw ranges; `plan_erase` with unknown alias raises `family-toolchain-erase-unsupported-region`; `execute_erase` reports `total_bytes_erased`; `open_monitor` pumps `MonitorEvent`s in order; `FakeProbe` records calls.
- [ ] 1.7 Add `tests/test_probe_orchestrator_contract.py` enforcing the entry-point dispatch invariant via AST scan: `commands/{reset,erase,monitor}.py`, `tui/screens/{debug,monitor}.py`, and the new MCP probe handlers MUST NOT spawn `probe-rs` / `openocd` directly nor import them — every dispatch goes through `probe_orchestrator`.

## 2. `alloy reset` Click command

- [ ] 2.1 Create `src/alloy_cli/commands/reset.py` with the Click command + flags (`--soft`/`--hard` mutex group, `--halt-after-reset`, `--probe`, `--project-dir`).
- [ ] 2.2 Dispatch through `probe_orchestrator.select_probe` + `reset_target`.  Output a Rich panel summarising probe id + method + duration on success.
- [ ] 2.3 Map the typed errors (`probe-not-attached`, `probe-multiple-attached`, `probe-unauthorised`, `probe-not-found`) to clean `click.ClickException` messages with cookbook links.
- [ ] 2.4 Register `reset_command` in `src/alloy_cli/main.py` (alongside `flash_command`).
- [ ] 2.5 Add `tests/test_command_reset.py`: `--help` advertises every flag; happy path uses `FakeProbe`; no probe → exit non-zero with the typed surface; multiple probes → typed surface lists them; vendor-only probe → typed surface naming the vendor tool; `--probe vid:pid:serial` selector wins over autodetect.

## 3. `alloy erase` Click command

- [ ] 3.1 Create `src/alloy_cli/commands/erase.py` with the Click command + flags (`--region` repeatable, `--auto`, `--yes`, `--probe`, `--project-dir`).
- [ ] 3.2 Implement `_should_prompt(auto, yes, tty)` + the confirmation prompt in the command.  Mirror Wave-3's `commands/new.py::_is_stdin_tty()` helper so tests can monkeypatch the TTY check without replacing `sys.stdin`.
- [ ] 3.3 Render the plan (Rich table: regions + total bytes + chip id) BEFORE the prompt fires.  Map `--region` arguments to the orchestrator's `regions` list (alias names + raw ranges).
- [ ] 3.4 Dispatch through `probe_orchestrator.{plan_erase, execute_erase}`.  Surface the typed errors (`family-toolchain-erase-{aborted, unsupported-region, probe-failed}`) as `click.ClickException`.
- [ ] 3.5 Register `erase_command` in `src/alloy_cli/main.py` (alongside `flash_command`).
- [ ] 3.6 Add `tests/test_command_erase.py`: `--help` advertises every flag; TTY + `y` answer executes the erase; TTY + `n` answer aborts with typed surface; `--auto` in non-TTY skips the prompt + executes; non-TTY without `--auto`/`--yes` aborts with a clear message; `--region bootloader` resolves IR alias; `--region 0x08000000-0x08010000` accepts the literal range; `--region not-a-region` raises typed surface.

## 4. `alloy monitor` Click command

- [ ] 4.1 Create `src/alloy_cli/commands/monitor.py` with the Click command + flags (`--port`, `--baud`, `--mode raw|rtt`, `--ansi/--no-ansi`, `--probe`, `--project-dir`).
- [ ] 4.2 Auto-detect the debug UART from `alloy.toml [uart].debug` when `--port` is not given.  When neither resolves, exit clean with a typed message.
- [ ] 4.3 Dispatch through `probe_orchestrator.open_monitor` with an `on_event` callback that streams `MonitorBytes` to stdout (with optional ANSI strip).
- [ ] 4.4 Catch `ProbeOperationCancelledError` (Ctrl+]) and print the one-line summary (`bytes_captured`, `duration_ms`, `last_line`).  Exit 0.
- [ ] 4.5 Register `monitor_command` in `src/alloy_cli/main.py`.
- [ ] 4.6 Run `python scripts/generate_cheatsheet.py` so the new verb lands in `docs/CHEATSHEET.md`.
- [ ] 4.7 Add `tests/test_command_monitor.py`: `--help` advertises every flag; explicit `--port` + `--baud` opens the right port; auto-detect via `alloy.toml [uart].debug` works; missing port + no project config exits with a clear error; Ctrl+] (simulated by `FakeProbe.close_session`) prints the summary line + exits 0; `--mode rtt` dispatches the RTT path.

## 5. TUI integration

- [ ] 5.1 Extend `src/alloy_cli/tui/screens/debug.py` with the action group: three `Button`s at the top of the layout (`Reset`, `Erase`, `Open Monitor`).  Use the same Wave-3 worker-thread pattern (`run_worker(thread=True)`).
- [ ] 5.2 Add the erase confirmation modal as a sub-`Screen` inside `tui/screens/debug.py` (or a new `tui/screens/erase_confirm.py`).  Renders the `ErasePlan` as a `DataTable` + `[Confirm]`/`[Cancel]` buttons.
- [ ] 5.3 Create `src/alloy_cli/tui/screens/monitor.py` with the live monitor screen: `RichLog` body, header with port/baud/mode + cumulative byte count, footer with bindings (`Ctrl+]` close, `Ctrl+L` clear).  Worker thread runs `open_monitor`; events stream back via `app.call_from_thread`.
- [ ] 5.4 Register the screen via `register_screen("monitor", title="Monitor", description=…)` so the command palette discovers it.
- [ ] 5.5 Refresh the SVG snapshot for the new `DebugScreen` action group (and add a `monitor.svg` snapshot for the new screen) — `pytest tests/test_snapshots.py --snapshot-refresh`.
- [ ] 5.6 Add `tests/test_tui_recovery_screens.py`: pressing `Reset` on `DebugScreen` dispatches the orchestrator (via `FakeProbe`); pressing `Erase` opens the modal; the modal's `[Confirm]` runs `execute_erase`; `MonitorScreen` opens at the configured port; Ctrl+] dismisses with the typed summary.

## 6. MCP integration (six new tools)

- [ ] 6.1 Add `_tool_probe_reset(registry, *, probe=None, method="soft", halt_after=False)` in `src/alloy_cli/mcp/tools.py`; project the `ResetReport` to JSON.
- [ ] 6.2 Add `_tool_probe_erase_plan(registry, *, probe=None, regions=None)`; project the `ErasePlan` to JSON.
- [ ] 6.3 Add `_tool_probe_erase(registry, *, probe=None, regions=None, confirm=False)`; refuse without `confirm=True` (raises `family-toolchain-erase-confirmation-required`); on accept dispatches `plan_erase` + `execute_erase`.
- [ ] 6.4 Add the session table + `_tool_probe_monitor_open` / `_probe_monitor_poll` / `_probe_monitor_close` handlers.  Sessions live in a process-global UUID-keyed dict; each session owns a background thread + a thread-safe byte buffer.  Idle sessions auto-close after 5 minutes (configurable for tests).
- [ ] 6.5 Register the six new tools in `_PARAM_SCHEMA` and `build_default_registry`'s handler dict.
- [ ] 6.6 Update `src/alloy_cli/integrations/opencode/system_prompt.md` with a "Canonical workflow for hardware bring-up" section: `probe_reset` is safe; `probe_erase` requires `probe_erase_plan` + `confirm=True`; `probe_monitor_open` returns a session id that must be polled + closed.
- [ ] 6.7 Add `tests/test_mcp_recovery.py`: every tool registered + JSON-serialisable; `probe_reset` happy path + typed error paths; `probe_erase_plan` returns the plan JSON; `probe_erase` without `confirm=True` raises typed; `probe_erase` with `confirm=True` dispatches; `probe_monitor_open` returns a session id; `probe_monitor_poll` returns incremental bytes; idle session times out.

## 7. Documentation

- [ ] 7.1 Author `docs/RECOVERY.md` covering the three commands + decision matrix + orchestrator API + Probe Protocol contract + two-phase MCP pattern + vendor-probe contract + cancellation contract + cross-links to Waves 1-3 docs.
- [ ] 7.2 Append a "Reset / Monitor" addendum to `docs/QUICKSTART.md` after the build/flash steps.  Mention `alloy erase` as the recovery option behind the safety gate.
- [ ] 7.3 Add `tests/test_recovery_doc.py` mirroring Wave 3's `test_toolchain_onboarding_doc.py`: every Wave-4 `error_type` is namedropped; every command has a subsection; every cookbook anchor is linked; QUICKSTART references `alloy reset` / `alloy monitor` / `alloy erase` and links to `RECOVERY.md`.
- [ ] 7.4 Update the `tests/test_toolchain_onboarding_doc.py` cross-link expectations if needed (RECOVERY.md is a sibling doc, not a child).

## 8. Validation + ship

- [ ] 8.1 Run `openspec validate add-recovery-tools --strict` and resolve every reported issue.
- [ ] 8.2 Run targeted test files locally and confirm green: `pytest tests/test_probe_orchestrator.py tests/test_probe_orchestrator_contract.py tests/test_command_reset.py tests/test_command_erase.py tests/test_command_monitor.py tests/test_tui_recovery_screens.py tests/test_mcp_recovery.py tests/test_recovery_doc.py tests/test_errors_uniqueness.py`.
- [ ] 8.3 Run `pytest -q --deselect tests/test_mcp_server.py::test_alloy_mcp_serve_stdio_round_trips_via_subprocess` (and the four pre-Wave-3 environmental deselects) and confirm green.
- [ ] 8.4 Run `ruff check src tests scripts` and `pyright src/alloy_cli` — fix any new findings introduced by this change.
- [ ] 8.5 Update `CHANGELOG.md` under `[Unreleased]` with a Wave-4 entry naming the new capability, the three new verbs (`alloy reset` / `alloy erase` / `alloy monitor`), the four new MCP probe tools, the TUI `MonitorScreen`, and the typed error vocabulary.
- [ ] 8.6 Open the PR titled `Implement add-recovery-tools (Wave 4 of toolchain-management)` referencing this OpenSpec change in the description.
