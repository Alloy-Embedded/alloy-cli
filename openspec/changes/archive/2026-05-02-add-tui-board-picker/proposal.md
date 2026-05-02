# Add TUI Board Picker

## Why

The Board Picker is the most-used screen for new users: it's how
they pick a target.  It also embeds inside the onboarding wizard.
Per `docs/TUI_DESIGN.md` Screen 2, this is a **faceted browser
with details pane** — search at the top, filters as chips, list +
detail card on the side.

## What Changes

- `tui.screens.BoardPickerScreen` — full layout per Screen 2.
- Reuses `FacetedFilter` widget from `add-tui-foundation`.
- Free-text search via `core.search.boards.search` (from
  `add-cli-boards-and-devices`).
- Detail pane with full `BoardManifest` rendering: identity,
  package, probe, debug UART, LED, button, clock, MCUboot, tier,
  example projects.
- `Tab` cycles focus: search → filter chips → board list → detail
  pane.
- `F2` expands detail into full-screen view with all `board.json`
  keys including the lower-level mcuboot / firmware_targets
  fields.

## Impact

A user can find their board in seconds without remembering the
exact `board_id`.  The screen embeds in the onboarding wizard so
new users discover targets visually.

## What this DOES NOT do

- No "search across bulk-admitted devices" — that's a separate
  screen (`tui.screens.DevicePickerScreen`, post-MVP).
- No "compare two boards" feature.
- No "favourite" / "pinned" boards — defer.
