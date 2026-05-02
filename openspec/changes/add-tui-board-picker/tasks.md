# Tasks — add-tui-board-picker

## Phase 1: Layout

- [ ] 1.1 `tui.screens.BoardPickerScreen` per `docs/TUI_DESIGN.md`
      Screen 2.
- [ ] 1.2 Search input bar wired to
      `core.search.boards.search(query, filters)`.
- [ ] 1.3 `FacetedFilter` instance wiring vendor / ISA / has /
      tier facets.
- [ ] 1.4 Board list with selection highlight + arrow-key nav.
- [ ] 1.5 Detail pane rendering full `BoardManifest`.

## Phase 2: Interactions

- [ ] 2.1 `↑↓` navigates list; selection live-updates detail pane.
- [ ] 2.2 `/` enters search mode (Textual `Input` focus).
- [ ] 2.3 `Tab / Shift+Tab` cycles focus zones.
- [ ] 2.4 `Space` toggles a focused filter chip; updates list
      live.
- [ ] 2.5 `Enter` selects the highlighted board → returns the
      `BoardSummary` to the caller (modal-style).
- [ ] 2.6 `F2` opens full-screen detail; `Esc` returns.

## Phase 3: Accessibility + degraded modes

- [ ] 3.1 80-column fallback: detail pane stacks below list.
- [ ] 3.2 NO_COLOR: glyphs replace tier / has-feature colour
      coding.
- [ ] 3.3 Tab order documented in screen docstring.

## Phase 4: Snapshot tests

- [ ] 4.1 Full catalogue render snapshot.
- [ ] 4.2 Filtered ("vendor=st") snapshot.
- [ ] 4.3 Search-mode active snapshot.
- [ ] 4.4 Detail view ("F2") snapshot.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 5.2 `openspec validate add-tui-board-picker --strict` passes.
- [ ] 5.3 Embed integration tested via Onboarding wizard step 2.
