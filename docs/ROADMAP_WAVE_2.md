# alloy-cli — wave 2 roadmap

After the 15-proposal initial roadmap closed (commits
`3a2f671..8592b3d`), `docs/REVIEW.md` flagged the gaps that block
a 1.0-quality release.  This document sequences the eight follow-
up OpenSpec proposals that close them.

## Phase summary

| # | Proposal | Phase | Tasks | Why this phase |
|---|----------|-------|-------|----------------|
| 16 | `add-codegen-integration` | 6 — Daily-driver completion | 17 | Closes the build-pipeline loop end-to-end (currently we run cmake without ever calling alloy-codegen). |
| 17 | `enrich-peripheral-kinds` | 6 | 24 | Extends typed validation from 4 kinds to 11; auto-DMA suggestion for uart/spi/i2c. |
| 18 | `add-real-update-pipeline` | 6 | 20 | Replaces the lockfile-only `alloy update` stub with real pip + git-submodule upgraders. |
| 19 | `add-tui-package-pinout` | 7 — Visual + observability | 20 | Per-package perimeter rendering — the CubeMX-class moment. |
| 20 | `add-tui-doctor-screen` | 7 | 17 | Textual DoctorScreen with `r` re-run + `f` auto-fix; `alloy doctor --fix`. |
| 21 | `add-clock-profile-persistence` | 7 | 17 | `[clocks].profiles` map + writeback from ClockTreeScreen. |
| 22 | `add-snapshot-test-harness` | 8 — Hygiene | 14 | Pin every TUI screen via pytest-textual-snapshot goldens. |
| 23 | `harden-release-and-injection` | 8 | 19 | Inject seam audit + single TOML emitter + release runbook + HIL CI. |

Total: **148 tasks across 8 proposals**.  Same shape, same OpenSpec
discipline as the wave-1 roadmap.

## Why this ordering

* **Phase 6** owns the "the daily-driver loop is complete" promise.
  Without #16 / #17 / #18 we ship a UI that's prettier than the
  underlying functionality.  Each proposal has at least one spec
  scenario today's code fails outright.
* **Phase 7** is visible polish.  The TUI looks good already; the
  three Phase-7 proposals upgrade it from "comparable to PlatformIO"
  to "comparable to CubeMX with AI on top".
* **Phase 8** is engineering hygiene that compounds.  Snapshot
  tests catch UI regressions the moment they land; the hardening
  proposal removes monkey-patch hostility, dedupes the TOML
  emitter, and seeds a release process.

## Closing the REVIEW.md punch list

| REVIEW.md item | Closed by |
|----------------|-----------|
| 1. Pinout schematic mode | #19 |
| 2. No codegen integration | #16 |
| 3. Build / Flash HIL missing | #23 |
| 4. Direct-import binding pattern | #23 |
| 5. Generic peripheral kinds are stubs | #17 |
| 6. DMA suggestion half-wired | #17 |
| 7. Clock tree edits don't persist | #21 |
| 8. DoctorScreen missing | #20 |
| 9. `alloy update` is a lockfile rewrite | #18 |
| 10. CI export YAMLs don't install arm-gcc | #18 (smoke gate) |
| 11. `_emit_toml` duplicated | #23 |
| 12. Private-attr access in tests | #23 |
| 14. No CHANGELOG | #23 |
| 15. No GH Actions wired | #23 |
| 16. Snapshot test pinning | #22 |

Items 13, 17, 18, 19, 20 (BLE001, accessibility audit, bulk
caching, GDB UI, telemetry) are deferred — none block 1.0.

## Recommended execution order

1. `add-codegen-integration` (#16) first — every other proposal
   benefits from the build pipeline being honest.
2. `add-real-update-pipeline` (#18) — once codegen is real, the
   update pipeline matters because users will actually need to
   pull new alloy-codegen versions.
3. `enrich-peripheral-kinds` (#17) — adds 7 typed kinds; piggy-
   backs on the schema bump that #21 also wants.
4. `add-clock-profile-persistence` (#21) — same schema bump,
   ships immediately after.
5. `add-tui-doctor-screen` (#20) — small, high-leverage; lands
   next.
6. `add-tui-package-pinout` (#19) — biggest visual win;
   schedule for a focused sprint.
7. `add-snapshot-test-harness` (#22) — pin everything we shipped,
   including the new screens.
8. `harden-release-and-injection` (#23) — final gate before 1.0.

This roadmap takes alloy-cli from "shipped but rough" to "1.0
ready for public launch".
