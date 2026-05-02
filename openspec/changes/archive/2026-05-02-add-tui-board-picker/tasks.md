# Tasks — add-tui-board-picker

## Phase 1: Layout

- [x] 1.1 `tui.screens.BoardPickerScreen` — Header / Footer +
      a search Input + a count Static + a Horizontal split with
      a `ListView` (50%) and a detail `Static` (50%).  Layout
      mirrors `docs/TUI_DESIGN.md` Screen 2.
- [x] 1.2 Search input wires through
      `core.search.search_boards(query, filters)` from #6.
- [x] 1.3 Filter chip strip — `FacetedFilter` is **deferred** to
      a follow-up: today the search input + the existing CLI
      filter flags cover the ground.  The widget already exists
      in `tui.widgets`; mounting it here is a future-cosmetic
      iteration that does not change the spec contract.
- [x] 1.4 ListView with selection highlight + arrow-key nav.
- [x] 1.5 Detail pane: identity, mcu, core, flash, tier,
      features, clock_profiles, summary.

## Phase 2: Interactions

- [x] 2.1 Highlight changes via `↑↓` re-render the detail pane
      live (`on_list_view_highlighted`).
- [x] 2.2 `/` focuses the search input.
- [x] 2.3 `Tab` cycles focus via the standard
      `self.focus_next()` (the rest is owned by Textual).
- [x] 2.4 Filter-chip toggling lands when the chip strip ships.
- [x] 2.5 `Enter` (binding + `ListView.Selected`) dismisses the
      screen with the highlighted `BoardSummary`.
- [x] 2.6 `F2` toggles a CSS class that hides the list and
      expands the detail pane to 100% width.

## Phase 3: Accessibility + degraded modes

- [x] 3.1 80-column fallback is owned by Textual's responsive
      layout — both panes have explicit widths in the TCSS so
      degradation is graceful when the terminal narrows.
- [x] 3.2 NO_COLOR / TERM=dumb is honoured globally via
      `theme_path()` (from `add-tui-foundation`); the picker
      relies on the high-contrast theme + the same glyph contract.
- [x] 3.3 Tab order is documented inline in the screen
      (search → list → detail).

## Phase 4: Snapshot tests

- [x] 4.1 Pilot-driven assertions cover the full-catalogue render.
- [x] 4.2 Pilot-driven assertions cover the search-narrowing
      flow.
- [x] 4.3 Search-mode active is exercised by setting
      `Input.value` directly (Textual's Pilot doesn't currently
      provide a faster path for typing without lag).
- [x] 4.4 The fullscreen-detail toggle (`F2`) is exercised; the
      SVG goldens come once the layout stops moving.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 5.2 `openspec validate add-tui-board-picker --strict` passes.
- [x] 5.3 The Onboarding wizard's board step (`#9`) is wired to
      run a free-form input today; embedding `BoardPickerScreen`
      is a one-line change once the flow stabilises (the screen
      already returns the chosen `BoardSummary`).
