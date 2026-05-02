# alloy-cli

> **Embedded firmware development without the IDE.**
> Pin picker, clock-tree visualiser, build/flash/debug, AI-assisted scaffolding —
> all in your terminal, all from a single tool.

`alloy-cli` is the developer-facing surface of the **Alloy embedded
platform**.  It replaces the dance of CubeMX (GUI) → IDE (closed
project format) → vendor flasher (per-chip) → CMake (write-it-yourself)
with one tool that:

- **Scaffolds** a working project from a board or chip name.
- **Configures** peripherals (UART / SPI / I²C / TIM / DMA / clocks)
  through an interactive terminal pin picker that rivals CubeMX —
  with the difference that every choice is validated against a
  **typed, schema-locked device IR** at config time.
- **Builds, flashes, debugs** with toolchain auto-detection (probe-rs,
  OpenOCD, J-Link, ST-Link, picoprobe) — without a CMake line in
  sight.
- **Talks to LLM agents** (Claude Code, opencode, Cursor, Continue)
  natively via **MCP** so `> "blink the LED"` becomes a working,
  type-checked patch instead of a hallucination.
- Ships a **searchable terminal UI** for boards, chips, peripherals,
  clocks, DMA matrix, memory map — all driven by the same canonical
  device IR the C++ HAL consumes.

## Why this exists

CubeMX has the right model and the wrong runtime — graphical, vendor-locked,
generates HAL code that isn't typed, configurations live in a `.ioc` file
nobody else can read.

PlatformIO has the right reach and the wrong precision — bag-of-strings
device data, no IR, no compile-time validation, configuration is a
`platformio.ini` of free-form keys.

Modm has the right philosophy and the wrong ergonomics — modular, scriptable,
~3 000 chips supported — but `lbuild build` is a developer's tool, not a
beginner's onboarding.

Zephyr `west` has the right scope and the wrong scope — fantastic for Zephyr,
unusable outside it.

`alloy-cli` is the merge: **CubeMX's pin-picker quality, Modm's chip
breadth, PlatformIO's beginner ergonomics, Cargo's developer
experience, plus AI agents native via MCP** — all running in the
terminal on the typed Alloy IR.

See `docs/COMPARISON.md` for the side-by-side.

## Status

Pre-zero.  The OpenSpec roadmap under `openspec/changes/` has the full
plan — 15 proposals across 5 phases.  Phase 1 is shipped (package
skeleton, data-source integration, project format) and Phase 2 is
underway (`alloy new` is implemented; build/flash/debug land next).

## AI integration

```sh
# Recommended host: opencode.  See docs/AI_INTEGRATION.md.
brew install sst/tap/opencode
alloy chat
# Or wire any other MCP client:
alloy chat --client claude-code
alloy chat --client cursor
```

`alloy chat` registers `alloy mcp serve` as the opencode MCP
source and loads our system prompt.  Type `"blink the LED"` →
the agent calls `list_boards → suggest_pins → add_gpio →
apply_diff → build` end-to-end.

## Quickstart

```sh
pip install alloy-cli  # (or `pip install -e .` from a dev checkout)

# 1. Scaffold a project from a board id
alloy new firmware --board nucleo_g071rb

# 2. Build
alloy build               # auto-detects toolchain, runs cmake + ninja
alloy build --profile release --clean

# 3. Flash (requires probe-rs + a connected probe)
alloy flash               # auto-selects when only one probe is connected
alloy flash --probe jlink

# 4. Debug — spawns probe-rs gdb-server + attaches your GDB front-end
alloy debug
alloy debug --gdb-ui /opt/gdb-multiarch

# 5. Daily-driver helpers
alloy doctor                         # diagnose host environment
alloy update --dry-run               # preview pinned-component upgrades
alloy export vscode                  # emit .vscode/{launch,tasks,c_cpp_properties}.json
alloy export ci --target github      # CI workflow for GitHub Actions
```

The scaffolder generates `alloy.toml`, a `CMakeLists.txt` that calls
`alloy_cli_init()`, a `src/main.cpp` that toggles the board's LED when
one exists, plus `README.md`, `.gitignore`, and a `LICENSE` of your
choice (`--license MIT|Apache-2.0|BSD-3`).  Build artefacts land under
`.alloy/build/` (gitignored), and a memory-summary line prints after
every successful build.

## Architecture (tl;dr)

Three façades over one core:

```
┌─── Click CLI         alloy add uart --tx PA9 --rx PA10 --dma
│                      (deterministic, scriptable, CI-friendly)
│
[ alloy core ops ]─────┼─── Textual TUI       alloy add uart  → pin picker
│   add_uart()         │                      (the differentiator)
│   list_boards()      │
│   query_ir()         └─── MCP server        opencode + LLM
│   flash()                                   (AI-assisted via tool use)
│   ...
```

Same operations, three entry points.  The CLI is scriptable, the TUI
is beautiful, the MCP server lets any AI agent (Claude Code,
opencode, Cursor, Continue) drive Alloy as if it were a power user.

See `docs/ARCHITECTURE.md`.

## Data sources (where the magic comes from)

`alloy-cli` is data-driven.  Every screen, every validator, every
suggestion is a query over canonical IR + project metadata that lives
elsewhere:

| Source | Repo | What |
|---|---|---|
| Canonical device IR | `alloy-devices-yml` | Per-chip schema-locked YAML (~17 admitted, 8 500 in `bulk-admitted/`) |
| C++ code generation | `alloy-codegen` | YAML → typed C++ headers + concepts |
| HAL + drivers + boards | `alloy` | The runtime firmware framework |
| Existing scaffolding | `alloy/tools/alloy-cli/` | First-cut Python CLI we extend / supersede |

See `docs/DATA_SOURCES.md` for the full mapping + how each source is
consumed.

## Roadmap

Five phases, 15 OpenSpec proposals, ~6 months of focused execution.
See `docs/ROADMAP.md` and `openspec/changes/`.

| Phase | Focus | Proposals |
|---|---|---|
| 1 — Foundation | Package, data integration, project format | 3 |
| 2 — Core CLI | new / build / flash / debug / boards / add | 4 |
| 3 — TUI experience | The Cube-MX-killer screens | 5 |
| 4 — AI surface | MCP server, opencode integration | 2 |
| 5 — Polish | doctor, update, export, advanced views | 1 |

## Contributing

`docs/CONTRIBUTING.md`.  Short version: every change goes through OpenSpec.

## License

TBD — most likely MIT or Apache-2.0 to match the rest of the Alloy
ecosystem.  Decision tracked in `openspec/changes/bootstrap-alloy-cli/`.
