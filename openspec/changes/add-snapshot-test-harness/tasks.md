# Tasks — add-snapshot-test-harness

## Phase 1: Render helpers

- [ ] 1.1 `tests/snapshots/_render.py` — extracts the
      board-catalog seeding / IR fixture / toolchain stubbing
      from `scripts/generate_docs_images.py` into reusable
      helpers.
- [ ] 1.2 `scripts/generate_docs_images.py` becomes a thin
      wrapper that calls the helpers and copies output into
      `docs/images/`.
- [ ] 1.3 No behavioural change to the developer workflow —
      `python scripts/generate_docs_images.py` still works.

## Phase 2: pytest-textual-snapshot wiring

- [ ] 2.1 `tests/conftest.py` registers the `snapshot` marker.
- [ ] 2.2 `tests/snapshots/` directory holds one `.svg` per
      pinned screen.
- [ ] 2.3 Each existing screen test gets a `@pytest.mark.snapshot`
      decorator + an `app.export_screenshot()` capture.
- [ ] 2.4 Comparison: failing tests print the path of the
      regenerated SVG so reviewers can `git diff` it.

## Phase 3: Initial goldens

- [ ] 3.1 Capture goldens for: Welcome / Dashboard / Onboarding
      / BoardPicker / PeripheralAdd / ClockTree / DmaMatrix /
      MemoryMap.
- [ ] 3.2 Commit each `.svg` under `tests/snapshots/`.

## Phase 4: CI integration

- [ ] 4.1 `pytest` already runs in `.github/workflows/ci.yml`;
      verify it picks up the new tests.
- [ ] 4.2 CI failure message: explicit hint to re-run with
      `pytest --snapshot-update` and commit the diff.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 5.2 `openspec validate add-snapshot-test-harness --strict`
      passes.
- [ ] 5.3 `docs/CONTRIBUTING.md` documents the snapshot refresh
      workflow.
