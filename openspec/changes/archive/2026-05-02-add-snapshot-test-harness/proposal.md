# Pin TUI Visual State With Snapshot Tests

## Why

The Pilot-driven tests assert structural state (`assert
"console" in joined_text`) but never compare against a pixel-
perfect golden image.  The 11 SVGs we generated for the docs are
the obvious starting point — a Textual screen change that drops
a column, swaps colours, or breaks layout is invisible to the
existing test suite.

`pytest-textual-snapshot` is already a dev dependency.  Wiring
it up gives us regressions-as-tests for every shipped screen.

## What Changes

### Snapshot harness

- `tests/snapshots/` — directory holding one
  `<screen-id>.svg` per pinned screen (initially: the 8 TUI
  screens shipped today plus the 3 CLI snippets via Rich).
- `tests/conftest.py` — pytest fixture wiring
  `pytest-textual-snapshot` to compare every Pilot test that
  opts-in via the `@snapshot` marker.
- Refresh workflow: `pytest --snapshot-update` regenerates the
  goldens; CI runs vanilla `pytest` and fails on any diff.

### Per-screen integration

- Every existing screen test gains a `@snapshot` marker so we
  start collecting goldens.
- New screens added by future proposals (Doctor screen, package
  pinout, etc.) ship with their goldens at proposal-archive
  time.

### Generator + harness convergence

- `scripts/generate_docs_images.py` is reorganised into:
  - `tests/snapshots/_render.py` — shared rendering helpers
    (build app, settle, export SVG).
  - `scripts/generate_docs_images.py` — thin wrapper that calls
    the helpers and copies the SVGs into `docs/images/`.
- That keeps `docs/images/` the public-facing copy and
  `tests/snapshots/` the test-pinning copy without duplicating
  the rendering logic.

### CI hook

- `.github/workflows/ci.yml` already runs pytest; no new job
  needed.  We add a CI-only failure message: "to update,
  re-run with `pytest --snapshot-update` and commit
  tests/snapshots/".

## Impact

A reviewer can read the SVG diff in a PR and immediately see
whether a screen change was intentional.  The `docs/images/`
gallery stays in sync because both surfaces share the rendering
helpers.

## What this DOES NOT do

- Does not introduce visual diff tooling beyond what
  `pytest-textual-snapshot` already provides.
- Does not snapshot the CLI Rich output (it's textual; the
  existing string-match tests are sufficient).  We only snapshot
  the Textual screens.
- Does not enforce snapshots for every Pilot test — only for
  screens whose layout we want to pin.  Modal-only or pure-logic
  tests opt out.
