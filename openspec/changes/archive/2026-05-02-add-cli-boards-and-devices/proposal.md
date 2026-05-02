# Add `alloy boards` and `alloy devices` Commands

## Why

Discoverability.  With ~17 admitted boards today and 8 500+ chips in
`alloy-devices-yml/bulk-admitted/`, a user needs a way to **find**
the right target before scaffolding.  `alloy boards` lists curated
boards (board.json-backed), `alloy devices` lists chips from the
canonical IR.  Both support search and filter facets.

These commands are the CLI counterpart of the TUI Board Picker
(Phase 3) — they share the same data layer and faceted filter
logic.

## What Changes

### `alloy boards [--search QUERY] [--vendor V] [--isa I] [--has FEATURE] [--tier N] [--json]`

- Lists boards from the loaded SDK catalogue.
- Free-text search matches `board_id`, `mcu`, `vendor`, `family`.
- Filter chips: `--vendor st`, `--isa cortex-m4`, `--has usb`,
  `--tier 1`.
- Output formats: human (default — Rich table), `--json` for
  scripting.
- `alloy boards <ID>` (positional) prints the board's full
  `BoardManifest` as a Rich-formatted detail card.

### `alloy devices [--search QUERY] [--vendor V] [--family F] [--admitted/--all] [--json]`

- Lists chips from `alloy-devices-yml`.
- `--admitted` (default): only chips in `vendors/`.
- `--all`: includes `bulk-admitted/`.
- Same search + filter pattern as `alloy boards`.
- `alloy devices <NAME>` prints the device's IR identity + summary
  + which boards reference it.

### Faceted filter logic

Lives in `core.search.{boards,devices}`.  Reused by:
- The `alloy boards / devices` CLI commands.
- The TUI Board Picker (Screen 2).
- The MCP tools `alloy.list_boards`, `alloy.list_devices`.

One implementation, three façades.

## Impact

Users can find what they need without leaving the terminal.  The
`--json` mode unlocks scripting (e.g., CI choosing a board from a
rotation) and AI-tool integration before MCP lands.

## What this DOES NOT do

- No interactive picker (TUI screen lives in `add-tui-board-picker`).
- No board admission flow (turning a `bulk-admitted/` chip into a
  `vendors/` admitted chip is a separate `alloy-devices-yml`
  workflow).
- No "compare boards" feature — defer.
