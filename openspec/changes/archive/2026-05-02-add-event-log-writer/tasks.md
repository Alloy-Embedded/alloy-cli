# Tasks — add-event-log-writer

## Phase 1: Core writer

- [x] 1.1 `core.events.EventLogger` dataclass + `append` method
      that JSON-encodes a `{timestamp, event, payload}` record
      (see `core.events.EventRecord`).
- [x] 1.2 `EventLogger.rotate_if_needed()` semantics live in
      `_rotate`, triggered when the file passes `MAX_LINES`
      (1024).
- [x] 1.3 `record_event(layout_or_path, event_type, **payload)`
      shared helper accepts either an `AlloyDir` or a project
      root `Path`; swallows `OSError` so a missing log line
      never crashes the caller.

## Phase 2: Integration

- [x] 2.1 CLI `_apply_diff` (`commands/add.py`) writes a
      `peripheral_added` event whenever an `--apply` lands a
      typed peripheral.
- [x] 2.2 `core.build.run` writes `build_started` (after the
      project loads) + `build_finished` for every code path
      including codegen failure, cmake failure, and ninja
      success.
- [x] 2.3 `core.flash.run` writes `flash_started` +
      `flash_finished` keyed on `probe`, `target`, and
      `returncode`.
- [x] 2.4 `core.update.apply_upgrades` writes
      `update_completed` per successful component (failures
      short-circuit so they don't claim success).
- [x] 2.5 `core.codegen._run_entry` writes
      `codegen_completed` after the stamp lands.
- [x] 2.6 The clocks save / activate flows emit
      `clock_profile_saved` /
      `clock_profile_activated` from the apply seam (TUI
      `_on_save_diff_applied`, MCP `apply_diff`).

## Phase 3: Façade wiring

- [x] 3.1 CLI `alloy add` writes the event after apply via
      `_apply_diff(... result=result)`.
- [x] 3.2 `tui.screens.PeripheralAddScreen.action_apply` and
      `tui.screens.ClockTreeScreen._on_save_diff_applied`
      both record events post-apply.
- [x] 3.3 MCP `apply_diff` records an event keyed on the
      cached diff's `proposed_summary` (peripheral_added /
      clock_profile_saved / clock_profile_activated).

## Phase 4: Tests

- [x] 4.1 `tests/test_event_log_writer.py` covers
      `EventLogger.append` round-trip, rotation past
      `MAX_LINES`, and the `record_event` `OSError` swallow.
- [x] 4.2 Build + flash integration tests assert the
      lifecycle events land in the JSONL with the expected
      `event` and `returncode` fields.
- [x] 4.3 Pilot test confirms the `Dashboard #dash-activity`
      panel renders a `peripheral_added` line.
- [x] 4.4 MCP test: `preview_diff` → `apply_diff` produces a
      `peripheral_added` event surfaced via
      `list_recent_events`.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/observability/spec.md`.
- [x] 5.2 `openspec validate add-event-log-writer --strict`
      passes.
