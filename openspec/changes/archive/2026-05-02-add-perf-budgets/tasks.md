# Tasks — add-perf-budgets

## Phase 1: Harness

- [x] 1.1 `pytest-benchmark>=5` added to
      `[project.optional-dependencies].dev` in `pyproject.toml`.
- [x] 1.2 `tests/conftest.py` registers the `perf` marker;
      `tests/perf/conftest.py` skips items unless `-m perf` is
      passed.
- [x] 1.3 `tests/perf/_budgets.py` declares the canonical
      budget table mirroring `ARCHITECTURE.md`, plus
      `effective_budget(label)` honouring
      `ALLOY_PERF_TOLERANCE` (defaults to the CI tolerance of
      1.25×).

## Phase 2: Suites

- [x] 2.1 `tests/perf/test_cli_startup.py` benchmarks
      `alloy --help`, `alloy --version`, and the
      `import alloy_cli.main` cold-start.
- [x] 2.2 `tests/perf/test_search.py` benchmarks
      `search_boards()` (warm) and
      `search_devices()` (admitted-only).
- [x] 2.3 `tests/perf/test_add.py` benchmarks an
      `add_uart` happy-path preview against an in-memory
      fixture.
- [x] 2.4 `tests/perf/test_tui_startup.py` Pilot-runs
      WelcomeScreen and asserts first paint stays inside 4×
      the TUI budget (Pilot setup overhead absorbed).
- [x] 2.5 `tests/perf/test_mcp_tools.py` exercises
      `list_boards`, `read_alloy_toml`, and
      `list_recent_events` round-trips.

## Phase 3: CI integration

- [x] 3.1 `.github/workflows/perf.yml` runs
      `pytest -m perf --benchmark-json=benchmark.json` on
      Ubuntu with `ALLOY_PERF_TOLERANCE=1.5` (extra slack on
      shared runners).
- [x] 3.2 The job uploads `benchmark.json` via
      `actions/upload-artifact@v4` with 30-day retention.
- [x] 3.3 `continue-on-error: true` initially while we tune
      thresholds; flip to `false` once the suite has settled
      one release cycle.

## Phase 4: Docs sync

- [x] 4.1 `tests/test_architecture_doc_sync.py` parses the
      `docs/ARCHITECTURE.md` performance table and asserts
      every cell matches `tests/perf/_budgets.py`.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/observability/spec.md`.
- [x] 5.2 `openspec validate add-perf-budgets --strict`
      passes.
