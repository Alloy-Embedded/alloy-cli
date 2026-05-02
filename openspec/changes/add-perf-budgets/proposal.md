# Enforce the Performance Budgets from ARCHITECTURE.md

## Why

`docs/ARCHITECTURE.md` declares hard performance budgets:

- `alloy --help` < 80 ms
- `alloy boards` (cached) < 200 ms
- `alloy add uart` (CLI happy path) < 500 ms
- TUI initial paint < 300 ms
- TUI screen switch < 50 ms
- MCP tool call < 100 ms

We have *zero* automated coverage of those budgets.  A
regression that doubles `alloy --help` (e.g. an eager import of
Textual) would slip through every gate.  CubeMX-class UX needs
budgets enforced — not just documented.

## What Changes

### Benchmark harness

- `tests/perf/` directory hosts pytest-benchmark suites:
  - `test_cli_startup.py` — `alloy --help`, `alloy --version`,
    `alloy doctor` cold-start.
  - `test_search.py` — `alloy boards`, `alloy devices` (warm +
    cold).
  - `test_add.py` — happy-path UART add, including the diff
    cache.
  - `test_tui_startup.py` — Pilot-driven `WelcomeScreen` first
    paint.
  - `test_mcp_tools.py` — `list_boards`, `query_device_ir`,
    `preview_diff` round-trip.

### Budget enforcement

- Each test asserts a budget via
  `assert benchmark.stats.mean < BUDGET_S` so the test fails
  loudly when it regresses.
- A central `tests/perf/_budgets.py` keeps the numbers; the
  `BUDGET_S` reference SHALL match the values in
  `ARCHITECTURE.md`.  A docs-sync test asserts the Markdown
  table and the Python dict agree.

### CI integration

- Perf job runs separately from the main test suite (it's
  noisy on shared GitHub runners, so we set a 1.25× tolerance
  for CI vs the local target).
- `pytest-benchmark --save=ci` archives results so we can
  build a regression chart later.

### Local override

- `ALLOY_PERF_TOLERANCE=2` env var multiplies every budget so
  contributors on slow laptops don't see false failures
  locally.  CI uses the canonical value.

## Impact

- A regression that doubles `alloy --help` startup blocks the
  PR with a clear "exceeded 80 ms (saw 156 ms)" message.
- The ARCHITECTURE.md table becomes a contract instead of a
  wish list.
- `pytest-benchmark` output gives reviewers a per-PR
  performance delta.

## What this DOES NOT do

- Does not introduce continuous flame-graph profiling — out
  of scope.
- Does not enforce per-call MCP latency at the protocol layer
  (we measure the registry's `call(...)` only).
- Does not gate budgets on the slow path (e.g. cold
  `bulk-admitted` parse — that's `add-bulk-search-cache`'s
  job).
