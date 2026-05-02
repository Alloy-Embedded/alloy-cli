# Tasks — add-event-log-writer

## Phase 1: Core writer

- [ ] 1.1 `core.events.EventLogger` dataclass + `append` method
      that JSON-encodes a `{timestamp, event, payload}` record.
- [ ] 1.2 `EventLogger.rotate_if_needed()` rolls the file to
      `events.jsonl.1` once it crosses 1024 lines.
- [ ] 1.3 `record_event(layout, event_type, **payload)` shared
      helper that constructs the logger lazily and swallows IO
      errors with a single `Diagnostic` (never crashes the
      caller).

## Phase 2: Integration

- [ ] 2.1 `core.peripherals.add_*` writes a `peripheral_added`
      event whenever the diff is non-empty AND error-free.
- [ ] 2.2 `core.build.run` writes `build_started` + `build_
      finished` events with `profile`, `returncode`, `elf_path`.
- [ ] 2.3 `core.flash.run` writes `flash_started` + `flash_
      finished` with `probe`, `target`, `returncode`.
- [ ] 2.4 `core.update.apply_upgrades` writes `update_completed`
      per successful component.
- [ ] 2.5 `core.codegen.{regenerate_if_stale,force_regenerate}`
      write `codegen_completed`.
- [ ] 2.6 `core.clocks.save_profile` / `activate_profile` apply
      paths write `clock_profile_saved` /
      `clock_profile_activated`.

## Phase 3: Façade wiring

- [ ] 3.1 CLI `alloy add` writes the event after apply.
- [ ] 3.2 `tui.screens.PeripheralAddScreen.action_apply` and
      `tui.screens.ClockTreeScreen._on_save_diff_applied` both
      record events.
- [ ] 3.3 MCP `apply_diff` records an event keyed on the
      cached diff's `proposed_summary`.

## Phase 4: Tests

- [ ] 4.1 Unit tests for `EventLogger.append` (round-trip,
      rotation, atomic append).
- [ ] 4.2 Integration tests confirming each mutating core op
      produces the expected event shape.
- [ ] 4.3 Pilot tests confirm `Dashboard #dash-activity` panel
      renders the most recent event after a mutation lands.
- [ ] 4.4 MCP test: a `preview_diff` → `apply_diff` flow
      produces a `peripheral_added` event surfaced via
      `list_recent_events`.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/observability/spec.md`.
- [ ] 5.2 `openspec validate add-event-log-writer --strict`
      passes.
