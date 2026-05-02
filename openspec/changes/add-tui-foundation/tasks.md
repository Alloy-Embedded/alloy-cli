# Tasks — add-tui-foundation

## Phase 1: App shell

- [ ] 1.1 `tui.app.TuiApp(textual.App)` — global bindings, screen
      stack, theme manager.
- [ ] 1.2 Screen registration mechanism (`@register_screen("name")`
      decorator) so the command palette discovers them.
- [ ] 1.3 `alloy ui` entrypoint launches `TuiApp`.

## Phase 2: Global widgets

- [ ] 2.1 `tui.widgets.CommandPalette` — Ctrl+P fuzzy search.
      Sources: registered screens, recent project events, CLI
      command index.
- [ ] 2.2 `tui.widgets.DiffWidget` + `tui.modals.DiffModal` —
      unified / side-by-side toggle, syntax highlighting via
      `rich.syntax`.
- [ ] 2.3 `tui.widgets.ValidationPanel` — Diagnostic list with
      colour + glyph.
- [ ] 2.4 `tui.widgets.ToolchainBadge` — small status pill.
- [ ] 2.5 `tui.widgets.FacetedFilter` — multi-section chip group.

## Phase 3: Theming

- [ ] 3.1 `tui/themes/default_dark.tcss` matching the colour
      contract from `docs/TUI_DESIGN.md`.
- [ ] 3.2 `tui/themes/high_contrast.tcss` for accessibility.
- [ ] 3.3 Theme picker via `--theme` and `$ALLOY_TUI_THEME` env.
- [ ] 3.4 `NO_COLOR` and `TERM=dumb` honoured (Textual handles
      most; we add tests).

## Phase 4: Snapshot harness

- [ ] 4.1 `tests/tui/snapshot_helpers.py` — `assert_screen_matches`
      helper using `pytest-textual-snapshot`.
- [ ] 4.2 Stable terminal-size + theme for snapshots (120×40
      default, `default_dark` theme).
- [ ] 4.3 CI gate: golden snapshots updated only via
      `pytest --update-snapshots` opt-in.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/tui-experience/spec.md` capturing
      the global keybindings + accessibility contract.
- [ ] 5.2 `openspec validate add-tui-foundation --strict` passes.
- [ ] 5.3 Manual smoke: `alloy ui` opens, `Ctrl+P` palette works,
      `Esc` exits cleanly.
