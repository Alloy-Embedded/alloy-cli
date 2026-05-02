# Test the TUI Accessibility Story End-to-End

## Why

`docs/TUI_DESIGN.md` and the post-launch `REVIEW.md` (item 17)
both promise:

- Glyph-paired colour cues so info is never colour-only.
- `NO_COLOR=1` and `TERM=dumb` honour-degradation.
- A 16-colour fallback theme (low-fidelity terminals).
- 80-column layout that keeps content readable.
- Screen-reader friendly widget labelling.

We honour `NO_COLOR` and `TERM=dumb` in `tui/theme.py` (the
theme switches to glyph-only palette).  *Nothing tests that
behaviour end-to-end.*  The screen-reader path has zero
coverage.  Layout breakage at 80 cols is unverified.  Without
tests, the claim that alloy-cli is accessible is just a
README bullet.

## What Changes

### Pilot-driven theme tests

- `tests/test_accessibility_themes.py` parametrises Pilot
  tests across `(default, no-color, dumb-term, 16-color)` and
  asserts:
  - Every state-bearing widget renders the matching glyph
    (no colour-only signalling).
  - SVG snapshots exist per theme under
    `tests/snapshots/accessibility/<screen>-<theme>.svg`.

### 80-column smoke

- A subset of the snapshot tests run at `size=(80, 30)` so
  the layout is provably readable on a stock terminal.
- The PinoutWidget falls back to compact mode at this width
  (already the contract); we now assert it.

### Screen reader probe

- `tests/test_accessibility_aria.py` walks every widget
  yielded by every shipped screen and asserts the widget
  carries a non-empty `tooltip` or `aria_label` (Textual
  exposes both via `get_loading_indicator()` /
  `widget.tooltip`).  Widgets that intentionally have no
  label (decorative dividers) are exempted via an explicit
  allow-list.

### Doctor entry

- A new `alloy doctor` check `accessibility-suite` reports
  whether `NO_COLOR` / `TERM` / colour profile look sane on
  the user's terminal — pointers, not gates.

## Impact

- Every shipped TUI screen has a glyph-only render under
  test; visual regressions in the accessible path surface
  immediately.
- 80-col layouts can't silently regress.
- Screen-reader users (or testers thereof) get widgets with
  meaningful labels.

## What this DOES NOT do

- Does not bring up a real screen-reader integration test
  (manual verification stays the bar).
- Does not change the public theme API; we just exercise
  what's already there.
- Does not introduce alternate colour palettes; the existing
  three (default, glyph-only, 16-colour) are enough.
