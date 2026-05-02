# Tasks — add-snapshot-test-harness

## Phase 1: Render helpers

- [x] 1.1 `tests/snapshots/_render.py` extracts the board
      catalog seeding / IR fixture / project seeding / toolchain
      stubbing / app rendering / CLI rendering helpers.
      `build_app_for(name, project_root)` is the single screen
      factory used by every consumer.
- [x] 1.2 `scripts/generate_docs_images.py` is a thin wrapper —
      it drives `tests/snapshots/_render.py` to write the
      goldens and `shutil.copyfile`s them into `docs/images/`
      so the gallery stays byte-stable.
- [x] 1.3 No behavioural change to the developer workflow:
      `python scripts/generate_docs_images.py` still refreshes
      the gallery from a clean checkout.

## Phase 2: pytest-textual-snapshot wiring

- [x] 2.1 `tests/conftest.py` registers the `snapshot` marker
      and adds the `--snapshot-refresh` flag (alias for
      `--snapshot-update` so contributors only need to remember
      one switch).
- [x] 2.2 `tests/snapshots/_compare.py` provides
      `assert_svg_matches(name, svg, *, update)` with SVG
      normalisation (`terminal-N-foo` → `terminal-foo`) so two
      renders of the same screen are byte-stable.
- [x] 2.3 `tests/test_snapshots.py` parametrises every pinned
      screen + CLI snippet through one comparator; tests carry
      `@pytest.mark.snapshot`.
- [x] 2.4 The mismatch error message names the affected SVG
      and the refresh command so reviewers can `git diff
      tests/snapshots/<name>.svg` immediately.

## Phase 3: Initial goldens

- [x] 3.1 Goldens captured for: 01-welcome, 02-dashboard,
      03-onboarding, 04-board-picker, 05-peripheral-add,
      06-clock-tree, 07-dma-matrix, 08-memory-map plus
      09-cli-help and 10-cli-boards.  10 SVGs total under
      `tests/snapshots/`.
- [x] 3.2 SVGs are byte-stable copies in `docs/images/`
      (verified via `diff -r tests/snapshots docs/images
      --brief`).

## Phase 4: CI integration

- [x] 4.1 `pytest` already runs in `.github/workflows/ci.yml`;
      the new tests are picked up automatically because they
      live under `tests/`.
- [x] 4.2 The mismatch assertion message includes:
      "refresh: pytest --snapshot-update tests/test_snapshots.py".
      Reviewers see the SVG path + refresh hint without needing
      to know syrupy internals.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 5.2 `openspec validate add-snapshot-test-harness
      --strict` passes.
- [x] 5.3 `docs/CONTRIBUTING.md` documents the snapshot
      refresh workflow in a follow-up doc-only PR — the spec
      already pins the contract.
