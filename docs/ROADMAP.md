# Roadmap

Five phases, fifteen OpenSpec proposals, ~6 months of focused
execution.  Each proposal is independently shippable; each phase
unlocks user-visible value.

## Phase 1 — Foundation (~3 weeks)

The plumbing.  Nothing user-visible; gets the project compilable,
CI-validated, and reading data from sibling repos.

| # | Proposal | Output |
|---|---|---|
| 1 | `bootstrap-alloy-cli` | pyproject, package skeleton, `alloy --version`, CI scaffold, license, code style |
| 2 | `integrate-data-sources` | Submodule alloy-devices-yml, helper to fetch alloy SDK + alloy-codegen, version-resolution |
| 3 | `define-project-format` | `alloy.toml` schema (versioned), `.alloy/` cache layout, CMake helper |

**Exit criteria**: `pip install alloy-cli` works.  Inside a manually-
written project with `alloy.toml`, `alloy --help` lists the planned
commands (most as stubs).

## Phase 2 — Core CLI (~5 weeks)

Deterministic, scriptable verbs.  No TUI yet.  Every command
emits human-readable output via Rich.

| # | Proposal | Output |
|---|---|---|
| 4 | `add-cli-new` | `alloy new <name> --board <id>` scaffolds project from templates |
| 5 | `add-cli-build-flash-debug` | `alloy build`, `alloy flash`, `alloy debug` with toolchain + probe detection |
| 6 | `add-cli-boards-and-devices` | `alloy boards [--search …]`, `alloy devices [--search …]` |
| 7 | `add-cli-add-peripheral` | `alloy add <kind>` IR-validated peripheral wiring (CLI flags only — no TUI yet) |

**Exit criteria**: Full happy path possible with no TUI.

```bash
$ alloy new firmware --board nucleo_g071rb
$ cd firmware
$ alloy add gpio --pin PA5 --mode output --label LED --apply
$ alloy build
$ alloy flash
```

This alone would put alloy-cli ahead of Modm/lbuild on UX, and ahead
of vendor IDEs on scriptability.  It's a complete product.

## Phase 3 — TUI experience (~10 weeks)

The Cube-MX-killer screens.  The differentiator.

| # | Proposal | Output |
|---|---|---|
| 8 | `add-tui-foundation` | Textual app shell, theming, command palette, diff modal, snapshot harness |
| 9 | `add-tui-dashboard-and-onboarding` | Dashboard + onboarding wizard (Screens 1, 12) |
| 10 | `add-tui-board-picker` | Board picker with faceted filters (Screen 2) |
| 11 | `add-tui-peripheral-assignment` | The killer screen — `PinoutWidget` + `ValidationPanel` (Screen 3) |
| 12 | `add-tui-clock-tree-and-build-flash` | Clock tree (Screen 4), live build (7), live flash (8) |

**Exit criteria**: A new user can scaffold a project and configure a
UART entirely without typing a CLI flag.  The TUI is published
in screenshots / videos.  Snapshot tests cover every screen.

## Phase 4 — AI surface (~3 weeks)

MCP server and recommended LLM agent integration.  This phase is
small in LOC because most of the work is the IR queries + add_*
operations already built in phases 1-3; we wrap them as MCP tools.

| # | Proposal | Output |
|---|---|---|
| 13 | `add-mcp-server` | `alloy mcp serve`, `mcp.alloy.*` tools (list, query_ir, add_*, build, flash) |
| 14 | `recommend-opencode-host` | `alloy chat` shortcut, opencode config bundle, system prompts / agents tuned for alloy IR |

**Exit criteria**: A user with opencode (or Claude Code) installed
can `alloy chat` and type "blink the LED" — get a working,
type-checked patch in under 30 s.  All MCP tool calls validated
against the IR; zero hallucinated register addresses.

## Phase 5 — Polish + advanced views (~4 weeks)

Power-user views and quality of life.

| # | Proposal | Output |
|---|---|---|
| 15 | `add-doctor-update-export` | `alloy doctor` (Screen 11), `alloy update`, `alloy export <ci\|vscode\|gdb>` |

Includes:
- DMA matrix screen (Screen 5)
- Memory map screen (Screen 6)

**Exit criteria**: alloy-cli is a polished daily-driver tool.
Issues that block adoption (missing toolchain handling, version
upgrade flows, "how do I integrate this with VS Code?") are
addressed.

---

## Sequencing rationale

- **Phase 1 must come first** — every later phase reads from data
  sources / project format defined here.
- **Phase 2 must come before Phase 3** — the TUI is a façade over
  the same operations the CLI exposes.  Build the operations once,
  ship two façades.
- **Phase 4 must come after Phase 2** — MCP tools wrap the same
  operations.  Without Phase 2, MCP would be wrapping nothing.
- **Phase 3 can theoretically swap with Phase 4**, but starting AI
  before the TUI means launching to a smaller addressable audience
  (LLM users).  TUI-first hits the broader "I just want to flash my
  Pico" segment first.
- **Phase 5 last** — power-user features.  Not blocking adoption.

## Total budget

| Phase | Weeks | Cumulative |
|---|---|---|
| 1 — Foundation | 3 | 3 |
| 2 — Core CLI | 5 | 8 |
| 3 — TUI | 10 | 18 |
| 4 — AI / MCP | 3 | 21 |
| 5 — Polish | 4 | 25 |

≈ 6 months of full-time work.  Halfway through (after Phase 2)
there's a complete, scriptable product.  After Phase 3 there's a
visually compelling product.  After Phase 4 there's a unique product
with no direct competitor.

## What we explicitly defer

- **Web UI / browser-based** — Textual supports a web target.  We
  wait until users ask.
- **Multi-board project layouts** — single-board v1.  Multi-board
  for OEMs / dev kits later.
- **Plugin system / 3rd-party drivers** — v1 is in-tree; plugins
  later.
- **Telemetry / usage analytics** — opt-in only, post-v1.
- **Vendor SDK bundling** — never bundle; always detect + suggest.

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Textual breaking changes | medium | pin `textual<X.Y` and run integration tests on upgrade PRs |
| MCP spec instability | medium | pin `mcp<X.Y`; keep MCP path optional |
| alloy-codegen API churn | high | pin `alloy-codegen<0.5` exactly, smoke-test on bump |
| alloy-devices-yml schema bumps | high | already encountered v1.5 → v2.1; loader supports both |
| User toolchain hell | high | `alloy doctor` in onboarding; clear install snippets |
| Build perf creeping over budget | medium | benchmarks in CI; <50 ms cmake overhead is enforceable |
| TUI snapshot churn | low | snapshots are golden files; CI gate prevents drift |
| Branding clash with `alloy/tools/alloy-cli` | high | Phase 1 includes the migration plan; the `tools/alloy-cli` becomes a thin shim |

## What success looks like

- 1k+ monthly active users by month 12.
- 100+ external contributors to alloy-devices-yml across vendors.
- Featured in major embedded conferences (Embedded World, FOSDEM,
  HackADay) by month 18.
- A reasonable share of new firmware projects bootstrap via `alloy
  new`.
- The MCP integration becomes the recommended way for AI agents to
  generate firmware.

We will not all-or-nothing this.  Ship Phase 2; let the world see
that.  Ship Phase 3; show off the TUI.  Iterate based on feedback.
