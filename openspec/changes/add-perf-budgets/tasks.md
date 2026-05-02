# Tasks — add-perf-budgets

## Phase 1: Harness

- [ ] 1.1 `pytest-benchmark` added to dev dependencies.
- [ ] 1.2 `tests/perf/conftest.py` configures the
      `ALLOY_PERF_TOLERANCE` env var and a `--perf` pytest
      marker so perf tests don't run by default.
- [ ] 1.3 `tests/perf/_budgets.py` declares the canonical
      budget table mirroring `ARCHITECTURE.md`.

## Phase 2: Suites

- [ ] 2.1 `test_cli_startup.py` benchmarks
      `alloy --help` / `alloy --version` / `alloy doctor`.
- [ ] 2.2 `test_search.py` benchmarks `alloy boards` (warm)
      and `alloy devices` (warm + cold).
- [ ] 2.3 `test_add.py` benchmarks an `add_uart` happy-path
      preview against an in-memory fixture.
- [ ] 2.4 `test_tui_startup.py` Pilot-runs WelcomeScreen and
      measures time-to-first-paint.
- [ ] 2.5 `test_mcp_tools.py` exercises `list_boards`,
      `query_device_ir`, and a `preview_diff → apply_diff`
      pair.

## Phase 3: CI integration

- [ ] 3.1 New `.github/workflows/perf.yml` runs `pytest -m
      perf` with the canonical tolerance.
- [ ] 3.2 The job archives `pytest-benchmark` JSON via
      `actions/upload-artifact`.
- [ ] 3.3 Perf job is marked `continue-on-error: false` once
      the suite stabilises (initially `true` for one release
      while we tune).

## Phase 4: Docs sync

- [ ] 4.1 `tests/test_architecture_doc_sync.py` parses the
      ARCHITECTURE.md performance table and asserts each
      cell matches `_budgets.py`.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/observability/spec.md`.
- [ ] 5.2 `openspec validate add-perf-budgets --strict`
      passes.
