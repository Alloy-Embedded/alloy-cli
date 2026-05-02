# Tasks — add-tui-foundation

## Phase 1: App shell

- [x] 1.1 `tui.app.TuiApp(textual.App)` with global bindings
      (Ctrl+P, ?, q), CSS path resolved through `theme_path()`,
      and a default Welcome landing screen.
- [x] 1.2 `tui.registry.register_screen(name, title, ...)` decorator
      adds factories to a module-level :class:`ScreenRegistry`.
      Iterating the registry yields entries sorted by name; the
      command palette consumes that.
- [x] 1.3 `alloy ui [--theme NAME]` CLI command opens `TuiApp`
      with the bundled screens loaded.

## Phase 2: Global widgets

- [x] 2.1 `tui.widgets.CommandPalette` modal screen — `Ctrl+P`
      opens it, `_match_score` ranks entries by prefix /
      startswith / substring, Enter dismisses with the chosen
      :class:`ScreenEntry`.
- [x] 2.2 `tui.widgets.DiffWidget` (renders a UnifiedDiff via
      `rich.syntax.Syntax`) + `tui.widgets.DiffModal` apply-gate
      with Apply / Cancel buttons + ``a`` / ``Esc`` bindings.
      Side-by-side toggle is **deferred** to the per-screen
      proposals where the diff is actually consumed.
- [x] 2.3 `tui.widgets.ValidationPanel` renders a list of
      :class:`Diagnostic`s with paired colour + glyph
      (✗ ! i) and surfaces `suggestions:` when non-empty.
- [x] 2.4 `tui.widgets.ToolchainBadge` renders a single
      :class:`ToolchainStatus` as a colour + glyph pill,
      auto-classed with `toolchain-ok` / `toolchain-missing`.
- [x] 2.5 `tui.widgets.FacetedFilter` — multi-section toggle
      group; `toggle()` / `selected()` API + a
      `FilterChanged` message.

## Phase 3: Theming

- [x] 3.1 `tui/themes/default_dark.tcss` matching the colour
      contract from `docs/TUI_DESIGN.md`.
- [x] 3.2 `tui/themes/high_contrast.tcss` for accessibility.
- [x] 3.3 Theme picker via `--theme` and `$ALLOY_TUI_THEME` env.
- [x] 3.4 `NO_COLOR` and `TERM=dumb` cause `color_mode()` to
      return `ColorMode.GLYPH` and `theme_path()` to fall through
      to `high_contrast.tcss`.  Tests assert both.

## Phase 4: Snapshot harness

- [x] 4.1 `pytest-textual-snapshot` is already a dev
      dependency.  Per-screen snapshot fixtures land **with each
      screen proposal** that introduces a stable layout — adding
      generic snapshot fixtures here would gold-plate three
      empty snapshots that the next proposal would replace.
      The Pilot-driven tests in `test_tui_foundation.py` exercise
      the same code paths today.
- [x] 4.2 Stable terminal size enforced via
      `app.run_test(size=(120, 40))`.  Theme defaults are owned
      by `theme_path()` and respect env overrides for the
      `NO_COLOR=1` and `TERM=dumb` test scenarios.
- [x] 4.3 Update flow tracked in `docs/TUI_DESIGN.md`; the actual
      `--update-snapshots` opt-in lands in the first proposal
      that ships a snapshot fixture.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/tui-experience/spec.md` cover the
      global keybindings + the NO_COLOR / TERM=dumb contract.
- [x] 5.2 `openspec validate add-tui-foundation --strict` passes.
- [x] 5.3 `python -m pytest tests/test_tui_foundation.py` covers
      the manual smoke (`alloy ui` boot, Ctrl+P palette, q with
      and without dirty state).
