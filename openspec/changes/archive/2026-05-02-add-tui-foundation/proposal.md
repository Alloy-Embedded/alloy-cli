# Add TUI Foundation

## Why

Phase 3 ships five TUI-heavy proposals.  Before any screen lands we
need the Textual app shell, the global widgets that every screen
reuses (command palette, diff modal, validation panel), the theming,
the snapshot test harness, and the keyboard-binding contract.

Doing this once, well, prevents per-screen reinvention.  See
`docs/TUI_DESIGN.md` for the design principles + custom widget
catalogue this proposal materialises.

## What Changes

- **`alloy_cli.tui.app.TuiApp`** — Textual `App` subclass with
  global keybindings (`Ctrl+P` palette, `?` help, `q` quit),
  screen stack, and theme switcher.
- **Global widgets** (`tui/widgets/`):
  - `CommandPalette` — `Ctrl+P` fuzzy search across every
    registered command.
  - `DiffWidget` + `DiffModal` — unified-diff viewer used by every
    "apply" flow.
  - `ValidationPanel` — colour-coded list of `Diagnostic`s.
  - `ToolchainBadge` — `✓ arm-gcc 13.2.0` style status pill.
  - `FacetedFilter` — multi-section toggle widget reused by
    Boards / Devices pickers.
- **Themes**: `default_dark.tcss` + `high_contrast.tcss`.
- **Snapshot test harness**: helper that runs a screen against a
  pilot, exports SVG, diffs against a golden.  Used by every
  per-screen proposal.
- **`alloy ui` entrypoint**: opens `DashboardScreen` (Phase 3.2)
  if inside a project, else `BoardPickerScreen` for ad-hoc
  exploration.
- **`alloy --tui` flag**: applies to commands that have an
  interactive variant (e.g., `alloy add uart --tui` opens the
  picker even if all CLI flags were given).

## Impact

Every later TUI proposal builds on this foundation: imports
`TuiApp`, registers a screen, reuses the diff modal, depends on
the snapshot harness.

## What this DOES NOT do

- No screens beyond a tiny stub.  Each Phase 3.2-3.5 proposal adds
  one or two.
- No web target.  Textual supports it; we defer.
- No bespoke theming UI; themes are .tcss files.
- No accessibility audit; we set the foundation (glyphs paired
  with colour, tab order documented) but the audit is in
  Phase 5 polish.
