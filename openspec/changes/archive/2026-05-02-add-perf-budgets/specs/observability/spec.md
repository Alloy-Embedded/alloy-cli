## ADDED Requirements

### Requirement: Performance budgets from ARCHITECTURE.md SHALL be enforced by an automated benchmark suite

A `tests/perf/` suite SHALL benchmark every entry point named
in `docs/ARCHITECTURE.md`'s performance table and SHALL fail
when the measured mean exceeds the documented budget multiplied
by the active tolerance.  The canonical budget table SHALL live
in `tests/perf/_budgets.py`; a docs-sync test SHALL assert that
the Python table and the ARCHITECTURE.md Markdown table agree.
CI SHALL run the suite in a dedicated job with a 1.25× tolerance
to absorb shared-runner noise; contributors MAY override the
tolerance locally via `ALLOY_PERF_TOLERANCE`.

#### Scenario: a startup regression blocks the PR

- **WHEN** a contributor lands an eager import in
  `alloy_cli.main` that pushes `alloy --help` startup past
  the 80 ms × 1.25 ceiling
- **THEN** the perf job SHALL fail
- **AND** the error message SHALL include the entry point
  name, measured mean, and the active budget

#### Scenario: contributors override tolerance locally

- **WHEN** a contributor runs
  `ALLOY_PERF_TOLERANCE=2 pytest -m perf`
- **THEN** every benchmark's effective budget SHALL be
  doubled
- **AND** the test header SHALL log the active multiplier so
  the override is visible in the output

#### Scenario: ARCHITECTURE.md and the Python table cannot drift

- **WHEN** a contributor edits the budget table in
  `ARCHITECTURE.md` without updating `_budgets.py` (or vice
  versa)
- **THEN** `tests/test_architecture_doc_sync.py` SHALL fail
- **AND** the failure SHALL list every mismatching row
