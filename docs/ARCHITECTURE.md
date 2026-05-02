# Architecture

Three façades over one core.

```
                          ┌─── Click CLI       alloy add uart --tx PA9 --rx PA10 --dma
                          │                    deterministic, scriptable, CI-first
                          │
   [ alloy-cli core ]─────┼─── Textual TUI     alloy add uart  → interactive picker
        │                 │                    information-dense, beautiful
        │                 │
        │                 └─── MCP server      opencode / Claude Code / Cursor
        │                                      LLM tool-use, AI-grounded
        ▼
[ canonical alloy IR ]
   alloy-devices-yml + alloy-codegen + alloy/boards/
```

## The three façades

| Façade | Tech | Audience | Use case |
|---|---|---|---|
| **CLI** | Click | scripts, CI, muscle memory | `alloy add uart --tx PA9 …` |
| **TUI** | Textual + Rich | interactive dev, learning | `alloy add uart` → picker |
| **MCP** | MCP SDK | LLM agents | "blink the LED" via tool calls |

All three call **the same core ops**.  Validation, business logic,
and IR queries are not duplicated across façades.

## The core layer

`src/alloy_cli/core/` is pure functions plus a small set of
dataclasses.  No I/O at module load.  Every function takes explicit
arguments and returns explicit results.  No global state.

Key modules (proposed):

```
src/alloy_cli/
├── core/
│   ├── ir.py              # query helpers over alloy-devices-yml IR
│   ├── boards.py          # board catalog (from alloy/boards/)
│   ├── project.py         # alloy.toml read/write/validate
│   ├── peripherals.py     # add_uart / add_gpio / add_spi / …
│   ├── clocks.py          # clock-graph queries + edits
│   ├── dma.py             # DMA channel allocator
│   ├── pins.py            # pin-assignment validator
│   ├── codegen.py         # alloy-codegen invocation wrapper
│   ├── build.py           # cmake/ninja invocation
│   ├── flash.py           # probe-rs / openocd dispatch
│   ├── debug.py           # gdb session launcher
│   ├── toolchain.py       # arm-gcc / clang detection + suggest
│   ├── diff.py            # unified diff renderer (used by TUI + CLI)
│   └── errors.py          # AlloyCliError hierarchy
├── cli/                   # Click commands — thin wrappers over core/
├── tui/                   # Textual app + screens
├── mcp/                   # MCP server — thin wrappers over core/
└── data/                  # local cache, downloaded artefacts
```

Each `core/` module is independently testable, importable from CLI /
TUI / MCP without circularity, and never reaches into a façade.

## Data sources (where info comes from)

See `DATA_SOURCES.md` for the long form.  Summary:

| Need | Source | Mechanism |
|---|---|---|
| Per-chip IR (peripherals, pins, clocks, registers, DMA) | `alloy-devices-yml/data/devices/.../*.yml` | git submodule **or** PyPI sidecar package `alloy-devices-yml-data` |
| C++ code generation | `alloy-codegen` (PyPI) | invoked as a subprocess: `alloy-codegen generate --device X --out Y/` |
| Board definitions (LED pins, debug UART, MCUboot offsets, …) | `alloy/boards/*/board.json` | submodule of `alloy/` (or fetched from pinned alloy version) |
| HAL source (drivers, includes) | `alloy/src/`, `alloy/drivers/` | CMake `find_package(alloy)` resolves on user's system |
| Existing first-cut CLI | `alloy/tools/alloy-cli/` | reference implementation we extend / supersede |

## Project format

`alloy.toml` at the user's project root is the single source of truth
for configuration.  Format:

```toml
# alloy.toml
[project]
name        = "my-firmware"
alloy-cli   = "0.5.0"          # min version of this CLI
alloy       = ">=0.7,<0.8"     # alloy/ HAL version range
alloy-codegen = ">=0.4,<0.5"   # codegen version range

[board]
id          = "nucleo_g071rb"  # or [chip] section for raw chip

[clocks]
profile     = "default_pll_64mhz"

[[peripherals]]
kind        = "uart"
name        = "debug"
peripheral  = "USART2"
tx          = "PA2"
rx          = "PA3"
baud        = 115200
# DMA optional; clocks pulled from board profile

[[peripherals]]
kind        = "uart"
name        = "app"
peripheral  = "USART1"
tx          = "PA9"
rx          = "PA10"
baud        = 115200
dma         = true              # → tx_dma, rx_dma auto-allocated

[[peripherals]]
kind        = "gpio"
name        = "led"
pin         = "PA5"
mode        = "output"

[build]
profile     = "release"
optimization = "size"            # size | speed | debug
lto         = true

[flash]
probe       = "auto"             # auto | jlink | stlink | picoprobe | …
```

`alloy.toml` is the **target** of every `alloy add` operation.  CMake
reads `alloy.toml` (via the alloy-cli helper) at configure time.  The
TUI is a `alloy.toml` editor.

The `.alloy/` directory inside the project holds derived state:

```
my-firmware/
├── alloy.toml              # source of truth
├── src/
│   └── main.cpp
├── CMakeLists.txt          # generated, slim — just calls alloy_cli_init()
├── .alloy/
│   ├── version.lock        # SHA pins for alloy / alloy-codegen / alloy-devices-yml
│   ├── generated/          # alloy-codegen output
│   └── cache/              # toolchain detection cache, etc.
└── README.md
```

## Versioning + reproducibility

`alloy.toml` declares version ranges.  `.alloy/version.lock` pins the
exact resolved versions.  A user committing both files gets bit-stable
builds across machines / CI / 3 months later.

`alloy update` upgrades one or more components and re-resolves the
lockfile.  `alloy build --frozen` refuses to upgrade.

## CMake integration

Generated `CMakeLists.txt` is intentionally minimal:

```cmake
cmake_minimum_required(VERSION 3.25)
project(my_firmware C CXX ASM)

include(FetchContent)
FetchContent_Declare(alloy_cli_helpers
    GIT_REPOSITORY https://github.com/Alloy-Embedded/alloy-cli
    GIT_TAG ${ALLOY_CLI_VERSION})
FetchContent_MakeAvailable(alloy_cli_helpers)

alloy_cli_init()              # reads alloy.toml, resolves alloy/, alloy-codegen/
add_executable(my_firmware src/main.cpp)
alloy_cli_link(my_firmware)   # links HAL + generated headers
```

The user owns this file but rarely needs to edit it.  Feature changes
flow through `alloy.toml`, not CMake.

## TUI shell

Textual app is one screen-stack with a global command palette
(`Ctrl+P`).  Every `alloy <subcommand>` that has interactive intent
mounts a screen.

```
TuiApp
├── DashboardScreen        # alloy ui (or alloy with no args inside a project)
├── BoardPickerScreen      # alloy new (board step), alloy boards
├── PeripheralAddScreen    # alloy add <kind>
├── ClockTreeScreen        # alloy clocks
├── DmaMatrixScreen        # alloy dma
├── MemoryMapScreen        # alloy memory
├── BuildLogScreen         # alloy build (live)
├── FlashScreen            # alloy flash (progress)
├── DiffModal              # global — confirms before any apply
├── CommandPalette         # global — Ctrl+P
└── HelpOverlay            # global — ?
```

Custom widgets (`tui/widgets/`):

```
PinoutWidget        # visual pin map of a package, click-to-select
ClockTreeWidget     # node-link diagram of clock graph
DmaMatrixWidget     # peripheral × channel grid
MemoryMapWidget     # stacked-bar memory layout
DiffWidget          # unified diff with syntax highlight
ToolchainBadge      # ✓ / ✗ status of detected toolchains
```

Each widget consumes a typed dataclass, never the raw IR.  This keeps
widgets dumb, the IR canonical, and tests cheap (snapshot rendering).

## MCP surface

`alloy mcp serve` starts an MCP server (stdio transport by default,
HTTP/SSE optional).  Tools exposed:

```
alloy.list_boards()                                      → BoardSummary[]
alloy.list_devices(vendor?, family?)                     → DeviceSummary[]
alloy.query_device_ir(device, peripheral_class?, …)      → IRView
alloy.suggest_pins(device, peripheral, signal)           → PinCandidate[]
alloy.add_uart(name, peripheral, tx, rx, dma?, baud?)    → AppliedDiff
alloy.add_gpio(name, pin, mode, label?)                  → AppliedDiff
alloy.add_spi(...)                                       → AppliedDiff
alloy.add_i2c(...)                                       → AppliedDiff
alloy.set_clock_profile(profile)                         → AppliedDiff
alloy.build()                                            → BuildResult
alloy.flash(target?)                                     → FlashResult
alloy.read_alloy_toml()                                  → ProjectConfig
alloy.preview_diff(operation, **args)                    → UnifiedDiff
```

Every `add_*` and `set_*` operation is **transactional**: returns a
diff for confirmation before applying.  The LLM's loop is "preview
→ confirm → apply"; opencode prompts can encode this as the standard
agent protocol.

## Observability

Every CLI invocation can emit a JSONL event log to
`.alloy/cache/events.jsonl`:

```json
{"ts": "2026-04-30T12:34:56", "op": "add_uart", "args": {…}, "result": "applied", "diff_lines": 12}
```

Useful for:
- Replaying user actions to reproduce bugs.
- Building a "session timeline" view in the TUI dashboard.
- Optional anonymous telemetry (off by default).

## Performance budget

| Op | Target |
|---|---|
| `alloy --help` | < 80 ms |
| `alloy boards` | < 200 ms (cached) |
| `alloy add uart` (CLI flags) | < 500 ms |
| TUI startup | < 300 ms to first paint |
| `alloy build` overhead | < 50 ms over raw cmake |
| MCP tool call (typical) | < 100 ms |

Achieved by:
- Lazy IR loading (only parse the device YAML you need).
- Lazy alloy-codegen invocation (only when a generated header is
  out-of-date).
- Caching board catalog + IR in `.alloy/cache/` with content-hashed
  invalidation.

## Testing

Three test layers:

1. **Unit tests** for `core/` — fast, no I/O.
2. **Snapshot tests** for TUI screens — use
   `pytest-textual-snapshot` to capture rendered output and diff on
   change.
3. **Smoke tests** for end-to-end flows — `alloy new --board pico` →
   `alloy build` → expect successful artefact.

## Failure modes + recovery

- **alloy-devices-yml missing**: `alloy doctor` prompts to fetch.
- **Toolchain missing**: `alloy doctor` suggests install command per
  OS.
- **Probe missing**: `alloy flash` lists available probes from
  probe-rs and prompts user to plug in or pick.
- **alloy.toml conflict**: `alloy add` operations fail loudly with a
  diff explaining the conflict; never silently overwrite.

## What's deliberately not architecture

- **No plugin system** in v1.  We can add one later if needed; for now
  every feature is in-tree.
- **No remote execution**.  Everything runs locally.  No telemetry by
  default.
- **No web UI**.  Terminal-first; web is hypothetical future work
  (Phase 6+).
- **No vendor SDK shipping**.  We detect arm-gcc / clang / esp-idf;
  we don't bundle them.
