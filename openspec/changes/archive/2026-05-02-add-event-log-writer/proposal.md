# Close the Event Log Writer Side

## Why

The Dashboard "Recent activity" panel and `alloy.list_recent_events`
MCP tool both read `.alloy/cache/events.jsonl`.  Nothing in the
codebase actually writes to that file.  Result: the panel
permanently shows `[dim]No events recorded yet.[/dim]`, and the
MCP tool always returns `[]`.

That's a broken contract.  Every mutating operation
(`add_*`, `build`, `flash`, `update`, `regenerate`,
`save_clock_profile`, `activate_clock_profile`) needs to drop one
JSONL line so the read path becomes meaningful.

## What Changes

### Core writer

- `core.events.EventLogger(layout: AlloyDir)` opens
  `.alloy/cache/events.jsonl` in append mode.
- `logger.append(event_type: str, **payload)` writes a single
  JSON object per line: `{"timestamp": ISO8601, "event":
  event_type, "payload": {...}}`.
- Append is atomic at the line level (`open(... "a")` +
  single `write()` call); concurrent writers never interleave
  mid-line.
- Auto-rotate when the file passes 1k lines: rename to
  `events.jsonl.1` (single rolling backup).

### Integration points

- `core.peripherals.add_*` → emit `peripheral_added` after the
  diff is applied (CLI / TUI / MCP all funnel through these).
- `core.build.run` → emit `build_started` + `build_finished`.
- `core.flash.run` → emit `flash_started` + `flash_finished`.
- `core.update.apply_upgrades` → emit `update_completed` per
  successful component.
- `core.codegen.regenerate_if_stale` /
  `core.codegen.force_regenerate` → emit `codegen_completed`.
- `core.clocks.save_profile` / `activate_profile` apply paths
  → emit `clock_profile_saved` / `clock_profile_activated`.

### Apply seam

The mutations above happen in three places:

1. CLI (`alloy add`, `alloy build`, …) — wrap the apply step.
2. TUI (PeripheralAddScreen, ClockTreeScreen) — wrap the
   `_write_diff` helper.
3. MCP (`apply_diff`) — wrap the registry's apply method.

A single `record_event(layout, event_type, payload)` helper
keeps these three call sites symmetrical.

## Impact

- Dashboard "Recent activity" panel comes alive on the first
  user action.
- `alloy.list_recent_events(limit=N)` MCP tool returns real
  data — agents can audit what they did across a session.
- A future `alloy events` CLI subcommand has a real backend to
  read from.

## What this DOES NOT do

- Does not introduce remote telemetry — writes are local-only.
- Does not introduce structured query / search — events are
  append-only JSONL, scanned linearly.
- Does not retain more than one rotated backup; multi-week
  retention belongs in a follow-up.
