# Tasks — add-accessibility-suite

## Phase 1: Theme test harness

- [ ] 1.1 `tests/test_accessibility_themes.py` parametrises
      every shipped screen across the four theme modes
      (default, NO_COLOR, TERM=dumb, 16-colour).
- [ ] 1.2 Per-theme SVG goldens land under
      `tests/snapshots/accessibility/<screen>-<theme>.svg`.
- [ ] 1.3 `tests/snapshots/_render.py` gains a
      `apply_theme(mode)` helper so the docs gallery script
      can produce the same SVGs for the public README.

## Phase 2: Glyph parity

- [ ] 2.1 `core.theme.glyph_for_state(state)` (already
      exists) gets a coverage test — every state in the
      enum maps to a non-empty glyph.
- [ ] 2.2 A render assertion: every `pin-state-*` /
      `severity-*` rendered cell carries the matching glyph
      (regex-based scan on the SVG).

## Phase 3: 80-column smoke

- [ ] 3.1 `tests/test_accessibility_layout.py` re-renders
      every pinned screen at `size=(80, 30)` and asserts
      no Static exceeds the available width.
- [ ] 3.2 PinoutWidget falls back to compact mode at width
      80 (regression test for the existing contract).

## Phase 4: ARIA / tooltip probe

- [ ] 4.1 `tests/test_accessibility_aria.py` walks every
      widget yielded by every shipped Screen and asserts
      `widget.tooltip` or `widget.aria_label` is non-empty.
- [ ] 4.2 An allow-list exempts decorative widgets
      (dividers, spacers); the list lives next to the test
      so reviewers see what's exempted.

## Phase 5: Doctor integration

- [ ] 5.1 `core.diagnose._accessibility_check` returns a
      `CheckResult` capturing NO_COLOR / TERM / 256-colour
      detection.
- [ ] 5.2 The check surfaces in `alloy doctor` and the TUI
      DoctorScreen with severity `info` (no auto-fix).

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 6.2 `openspec validate add-accessibility-suite
      --strict` passes.
