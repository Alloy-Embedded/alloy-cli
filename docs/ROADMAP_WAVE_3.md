# Wave 3 — From "Shipped" to "Truly Usable"

Wave 1 (15 proposals) shipped the surface area; wave 2 (8
proposals) hardened the contracts and closed every P0 / P1
item from `docs/REVIEW.md`.  Wave 3 closes the remaining gaps
between *"shipped"* and *"a brand-new user can land, blink an
LED, and trust the tooling"*.

The 8 proposals below are scoped to land in 5–10 working days
each; together they take alloy-cli from ~92% of its declared
vision to 100%.

## Sequencing

```
Phase 9 — Observability (foundation)
├── #24 add-event-log-writer        ── close the JSONL writer side
└── #25 add-perf-budgets            ── enforce ARCHITECTURE.md SLAs

Phase 10 — Hardening (parallel-safe)
├── #26 harden-error-handling       ── kill bare `except Exception`
├── #27 add-bulk-search-cache       ── drop bulk search to <100ms
└── #28 add-export-ci-toolchain-matrix ── arm-gcc in generated YAMLs

Phase 11 — DX completion (sequential)
├── #29 add-quickstart-and-cookbook ── 5-min path + examples + errors
└── #30 add-accessibility-suite     ── NO_COLOR / TERM=dumb / ARIA

Phase 12 — Debugger surface
└── #31 enrich-alloy-debug-tui      ── DebugScreen + GdbSession
```

Phase 9 is foundational — the event log + perf benchmarks
underpin downstream observability claims.  Phase 10 is
parallel-safe (three small proposals, no shared seams).  Phase
11 sits on top of phases 9–10 because the cookbook references
the new error types and the accessibility suite touches the
snapshot harness.  Phase 12 is the largest single proposal;
keep it last so reviewers can take their time.

## Per-proposal punchlist

### #24 `add-event-log-writer`
Closes: VISION.md observability promise; REVIEW.md item 6
(events.jsonl read-but-never-write).
**Touches:** `core.events` (new), every mutating core op,
Dashboard panel, MCP list_recent_events.
**Test surface:** ~12 cases.

### #25 `add-perf-budgets`
Closes: ARCHITECTURE.md performance table being aspirational.
**Touches:** new `tests/perf/`, `pytest-benchmark` dev dep,
new `.github/workflows/perf.yml`.
**Test surface:** ~10 benchmark cases + 1 docs-sync test.

### #26 `harden-error-handling`
Closes: REVIEW.md item 13 (10 bare `except Exception` sites).
**Touches:** new `core.log`, every offending site, ruff config
(re-enable BLE001).
**Test surface:** ~15 narrow-except tests + 4 logger tests.

### #27 `add-bulk-search-cache`
Closes: REVIEW.md item 18 (bulk device search ~7s).
**Touches:** `core.search` (new `_BulkCache`), `.alloy/cache/`
layout.
**Test surface:** ~6 cases including the <100ms benchmark.

### #28 `add-export-ci-toolchain-matrix`
Closes: REVIEW.md item 10 (CI YAMLs missing arm-gcc).
**Touches:** `core.export.github_workflow`, new
`_toolchain_step` selector, `--dry-run` flag.
**Test surface:** ~6 cases (snapshot per core, actionlint).

### #29 `add-quickstart-and-cookbook`
Closes: VISION.md Phase 6 docs promise.
**Touches:** `docs/QUICKSTART.md`, `docs/EXAMPLES/{01-blinky,
02-uart-echo, 03-spi-flash, 04-dma-double-buffer}/`,
`docs/ERROR_COOKBOOK.md`, `docs/CHEATSHEET.md`,
`scripts/generate_cheatsheet.py`, new
`alloy new --from-example`.
**Test surface:** ~8 cases + markdown lint.

### #30 `add-accessibility-suite`
Closes: REVIEW.md item 17; TUI_DESIGN.md accessibility claims.
**Touches:** new `tests/test_accessibility_*` suites,
`tests/snapshots/accessibility/`, doctor's
accessibility-suite check.
**Test surface:** ~20 cases (every screen × 4 themes).

### #31 `enrich-alloy-debug-tui`
Closes: REVIEW.md item 19; promotes alloy debug to TUI.
**Touches:** new `core.gdb`, new `tui.screens.DebugScreen`,
extended `commands.debug`.
**Test surface:** ~15 cases (MI2 parser + Pilot tests).

## Quality gates after wave 3

| Gate | Today | After wave-3 |
|---|---|---|
| Tests | 440 | ≈ 530+ |
| Ruff | clean (BLE001 disabled) | clean (BLE001 enabled) |
| Pyright | 0/0/0 | 0/0/0 |
| Perf budgets | none | 5 enforced |
| Snapshot screens | 10 | ≈ 50 (10 × 4 themes + 10 base) |
| Error types covered | 12 | 12 + cookbook anchor each |

## Sequencing rationale

- **#24 + #25 first** so subsequent proposals can rely on
  the event log (e.g. #29's quickstart asserts events fire).
- **#26 before #29** because the cookbook documents typed
  errors — those have to exist properly first.
- **#27 + #28 in parallel** with #26 since they touch
  unrelated paths.
- **#30 after #29** because accessibility tests reuse the
  snapshot harness #22 set up plus the cheatsheet generator
  from #29.
- **#31 last** — biggest scope, benefits from the polished
  error / log seams above.

## What this wave deliberately defers

- **Telemetry / opt-in metrics** — VISION.md flags as out of
  scope.
- **Plugin system** — explicit non-goal in v1.
- **Web UI** — VISION.md commits to terminal-first.
- **Vendor SDK bundling** — detection over bundling.
- **Multi-board kitchen-sink example** — wave-4.
- **Static documentation site** — Markdown stays canonical.
- **Reverse / record-replay debugging** — #31 explicitly
  excludes it.
- **Multi-host MCP bridge** — out of scope today.

After wave 3 the CLI is feature-complete relative to the
declared vision.  Wave 4 (if any) is product growth — new
peripheral kinds, new vendor families, new export formats.
