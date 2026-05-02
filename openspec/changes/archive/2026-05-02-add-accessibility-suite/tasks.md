# Tasks — add-accessibility-suite

## Phase 1: Theme test harness

- [x] 1.1 `tests/test_accessibility.py::test_color_mode_*`
      cover the four environment branches
      (default / NO_COLOR / TERM=dumb / explicit
      ALLOY_TUI_THEME) hitting the ColorMode enum.
- [x] 1.2 `theme_path()` falls back to `high_contrast`
      under glyph mode and `default_dark` otherwise — both
      branches asserted.
- [x] 1.3 `tests/snapshots/_render.py` is reused so the
      tests share the same render path as the docs gallery.
      A future doc-only PR can extend goldens to a full
      10x4 matrix (deferred — the core glyph-parity claim
      already has automated coverage).

## Phase 2: Glyph parity

- [x] 2.1 `glyph_for_severity` maps every severity
      (`error`, `warning`, `info`) to a distinct, non-empty
      glyph.
- [x] 2.2 The status-glyph palette
      (OK / FAIL / PRESENT / ABSENT / INFO / NEXT) is
      pinned to six distinct one-char strings — any
      regression breaks the test.

## Phase 3: 80-column smoke

- [x] 3.1 Representative screens (Welcome / Dashboard) are
      re-rendered at `size=(80, 30)` and asserted to
      produce a non-empty SVG.

## Phase 4: ARIA / tooltip probe

- [x] 4.1 `test_every_interactive_widget_has_a_label`
      walks the PeripheralAddScreen and asserts every
      `Button` / `Input` carries either `tooltip`,
      `aria_label`, or `placeholder`.
- [x] 4.2 The two surviving unlabeled buttons (`diff-button`
      / `apply-button`) gained tooltips that explain what
      they do.

## Phase 5: Doctor integration

- [x] 5.1 `core.diagnose._accessibility_check` returns a
      `CheckResult` summarising NO_COLOR / TERM /
      COLORTERM environment values.
- [x] 5.2 The check ships with severity `info` and
      `auto_fix=None`; surfaces in `alloy doctor` (CLI +
      DoctorScreen).

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 6.2 `openspec validate add-accessibility-suite
      --strict` passes.
