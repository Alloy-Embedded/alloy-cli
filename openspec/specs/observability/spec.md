# observability Specification

## Purpose
TBD - created by archiving change add-event-log-writer. Update Purpose after archive.
## Requirements
### Requirement: Mutating core operations SHALL write a structured event to .alloy/cache/events.jsonl

Mutating core operations SHALL append exactly one JSON object
per invocation to `.alloy/cache/events.jsonl` after the side
effect succeeds.  The set of mutating operations covered SHALL
include `add_*`, `build`, `flash`, `update`, `regenerate`,
`save_clock_profile`, and `activate_clock_profile`.  Each
record SHALL carry an ISO-8601 `timestamp`, a stable `event`
type string, and a `payload` object describing the arguments
and outcome.  Append SHALL be atomic at the single-line level
so concurrent writers never interleave.  The file SHALL roll
to `events.jsonl.1` once it crosses 1024 lines.

#### Scenario: a successful add_uart writes one peripheral_added record

- **WHEN** the user runs `alloy add uart console --peripheral
  USART2 --tx PA2 --rx PA3` and the diff applies cleanly
- **THEN** `.alloy/cache/events.jsonl` SHALL gain one new line
  whose JSON `event` field is `"peripheral_added"` and whose
  `payload.kind` is `"uart"`
- **AND** the line SHALL parse via `json.loads` without errors

#### Scenario: a failing build still records build_started and build_finished

- **WHEN** `alloy build --profile debug` exits non-zero
  (cmake fails)
- **THEN** the JSONL SHALL contain a `build_started` record
  followed by a `build_finished` record
- **AND** the `build_finished` payload SHALL include
  `returncode != 0` and the captured stderr tail

#### Scenario: file rotates after 1024 lines

- **WHEN** `events.jsonl` already has 1024 lines and a new
  mutating op runs
- **THEN** the existing file SHALL be renamed to
  `events.jsonl.1` (replacing any prior backup)
- **AND** the new event SHALL land in a fresh `events.jsonl`
  containing exactly one line

### Requirement: The Dashboard activity panel and MCP list_recent_events SHALL surface the same records

Both surfaces SHALL read from `.alloy/cache/events.jsonl` (no
separate event store).  The Dashboard activity panel and the
`alloy.list_recent_events` MCP tool SHALL display the
most-recent N entries newest-first and SHALL parse the JSON
payload into structured fields rather than raw text.

#### Scenario: dashboard reflects an event written by add_gpio

- **WHEN** the user adds a GPIO via the TUI
- **AND** opens the dashboard
- **THEN** the "Recent activity" panel SHALL show a row whose
  text starts with the ISO timestamp and contains
  `peripheral_added` plus the GPIO's `name` field

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

