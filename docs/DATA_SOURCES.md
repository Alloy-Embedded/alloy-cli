# Data Sources

`alloy-cli` doesn't carry chip data, board data, or codegen logic.
It composes them from four sibling repos.  This document is the
reference for **where every piece of information comes from**, **how
we read it**, and **how we keep them in sync**.

## The four pillars

| Repo | Role | Status (Apr 2026) |
|---|---|---|
| `alloy-devices-yml` | Canonical IR per chip + admission registry | 17 admitted, 8 505 pre-staged |
| `alloy-codegen` | YAML → typed C++ headers | mature, ~30 emitter classes |
| `alloy` | C++23 HAL + drivers + boards | ~9 000 source files |
| `alloy/tools/alloy-cli` | First-cut Python scaffolder | exists, partially implemented |

`alloy-cli` (this repo) consumes all four.  We do not duplicate any of
their data or logic.

---

## 1. `alloy-devices-yml` — the canonical IR

### Location
`https://github.com/Alloy-Embedded/alloy-devices-yml`

### Layout
```
alloy-devices-yml/
├── vendors/                    # ADMITTED chips (17 today)
│   └── <vendor>/<family>/devices/<device>.yml
├── bulk-admitted/              # PRE-STAGED chips (8 505 today)
│   └── <source>/<vendor>/<family>/<device>.yml
├── schema/
│   └── canonical_device/       # JSON Schema v1.5 (current)
│   └── canonical_device_v2_1/  # in development
├── index.yml                   # admission registry
└── tools/validate_all_yamls.py
```

### What we read
For a given device, **every field of the IR is potentially queried**:

| IR field | Where used in alloy-cli |
|---|---|
| `identity` | board picker, `alloy doctor` |
| `peripherals[]` | peripheral browser, `alloy add` |
| `pins[]` + `pin_signals[]` | pin picker, validity gates |
| `connection_candidates[]` | "what pins can do USART1_TX?" |
| `clock_nodes` + `clock_selectors` + `clock_gates` | clock-tree TUI |
| `peripheral_clock_bindings[]` | "what clock feeds USART1?" |
| `dma_routes[]` + `dma_bindings[]` | DMA matrix TUI, allocation |
| `interrupt_bindings[]` + `vector_slots[]` | interrupt picker |
| `memories[]` | memory-map TUI, linker config |
| `i2c_speed_options[]` | I²C config validity |
| `uart_baud_clock_sources[]` + `uart_max_baud_hz` | UART baud check |
| `*_mode_flags` | feature gating ("does this chip have FIFO?") |
| `register_fields[]` | optional power-user view |

### How we read it
**v1 distribution: git submodule**
```
alloy-cli/
└── data/devices/        # → alloy-devices-yml@<sha> as submodule
```

CMake / Python loaders read `data/devices/.../device.yml` directly.
Same pattern alloy-codegen uses today.

**v2 distribution: PyPI sidecar package** (post-MVP)
```
pip install alloy-devices-yml-data==1.5.3
```
Vendored YAMLs ship as data files inside the wheel.  Faster install,
no git required, but locks the user to one IR snapshot per release.
We support both: `--data-source submodule | package | path`.

**Cache**: parsed IR is cached in `.alloy/cache/ir/<device>.pickle`
keyed by `<device-sha, alloy-cli-version>`.  Invalidated on either
change.  Cuts repeat parsing of a 48 KB YAML to ~5 ms.

### Validation
We run alloy-devices-yml's `tools/validate_all_yamls.py` as part of
CI.  Any device that fails its own schema validation is excluded from
admission and never appears in the TUI / CLI.

---

## 2. `alloy-codegen` — the C++ emitter

### Location
`https://github.com/Alloy-Embedded/alloy-codegen`

### Role for alloy-cli
**alloy-cli is a consumer of alloy-codegen, not a re-implementation.**

The code generator already knows how to turn an IR into:
- `runtime/types.hpp`
- `runtime/peripheral_instances.hpp`
- `driver_semantics/uart.hpp`
- `driver_semantics/spi.hpp`
- … 30+ headers per device

When the user runs `alloy build`, alloy-cli does:

1. Resolve target device from `alloy.toml`.
2. Check `.alloy/generated/<device>/.stamp` — has the device YAML or
   alloy-codegen version changed since last gen?
3. If yes: invoke `alloy-codegen generate --device <X> --out
   .alloy/generated/<device>/`.
4. Pass the generated headers' include path to CMake.

### How we invoke it
**v1: subprocess**
```python
subprocess.run([
    "alloy-codegen", "generate",
    "--device", "stm32g071rb",
    "--out", ".alloy/generated/stm32g071rb",
    "--data-root", str(devices_yml_root),
], check=True)
```

**v2: in-process import** (when alloy-codegen is pip-installed
alongside alloy-cli)
```python
from alloy_codegen.cli import generate
generate(device="stm32g071rb", out=".alloy/generated/...")
```

In-process is faster (no Python startup × N devices) but couples
versions.  We support both behind `--codegen-mode subprocess|inproc`.

### Version pinning
`alloy.toml` declares `alloy-codegen = ">=0.4,<0.5"`.  `alloy-cli`
resolves it via:

1. `pip show alloy-codegen` — if a compatible version is installed,
   use it.
2. Else, prompt: "alloy-codegen 0.4.x not found.  Install? `pip
   install 'alloy-codegen>=0.4,<0.5'`"

The prompt is silent in CI when `--non-interactive` is set; instead
exits with a clear error.

---

## 3. `alloy` — the HAL repo

### Location
`https://github.com/Alloy-Embedded/alloy`

### What we read
- **`boards/`** — every `board.json` is a meta-descriptor:
  `{ vendor, family, device, arch, mcu, flash_size, debug_uart,
  leds[], buttons[], clock_profiles[], firmware_targets[],
  mcuboot{} }`
- **`drivers/`** — list of available drivers (display, filesystem, …)
  for the `alloy add driver <kind>` command.
- **`src/include/alloy/`** — used to confirm a HAL version exposes a
  given feature when version-resolving `alloy.toml`.

We do **not** parse `alloy/src/*.cpp` source.  We trust the
`board.json` + driver index.

### How we read it
**v1: assume `alloy/` is checked out at `~/.alloy/sdk/<version>/`**
The user runs `alloy sdk install <version>` once (existing
`alloy/tools/alloy-cli` already implements this); alloy-cli
inspects the cache.

**v2: alloy ships a `boards-manifest.json` in releases** — a single
JSON file with the union of every `board.json` for that release.
Faster lookup, smaller download.

### Reuse from `alloy/tools/alloy-cli`
The existing first-cut CLI in `alloy/tools/alloy-cli/` already has:

- `sdk.py` — SDK download / cache logic
- `toolchains.py` — toolchain detection stubs
- `_boards.toml` — board catalogue snapshot
- `_toolchain_pins.toml` — toolchain version pins
- `scaffold.py` + `_templates/` — Jinja2 project templates
- `alloy new` / `alloy boards` / `alloy sdk install` commands

**We move that code into this repo** as part of the
`bootstrap-alloy-cli` proposal.  The original `alloy/tools/alloy-cli/`
becomes a thin shim that prints a deprecation notice + delegates to
the new one, then is removed in a follow-up.

---

## 4. `alloy/tools/alloy-cli` — the first-cut Python CLI (THIS repo's predecessor)

### Status
~1 500 LOC, partial implementation.  Already does:

| Feature | State |
|---|---|
| `alloy new` | ✓ scaffolds via Jinja2 |
| `alloy boards` | ✓ lists boards from `_boards.toml` |
| `alloy sdk install <version>` | ✓ downloads + caches alloy SDK |
| Toolchain detection stubs | partial |
| Project format | basic (no `alloy.toml` schema) |
| TUI | none |
| MCP | none |
| `alloy build / flash / debug` | none |

### Migration plan
**Step 1** (`bootstrap-alloy-cli` proposal): move the four Python
modules above into `alloy-cli/src/alloy_cli/` and the templates into
`alloy-cli/src/alloy_cli/templates/`.

**Step 2** (`define-project-format` proposal): introduce the
`alloy.toml` schema + migrate `alloy new` templates to produce it.

**Step 3** (`add-cli-build-flash-debug` proposal): add the missing
commands.

**Step 4** (after parity): remove `alloy/tools/alloy-cli/` from the
`alloy/` repo with a single deprecation commit pointing to this repo.

We don't fork-and-diverge.  We **lift and replace**.

---

## Cross-repo version resolution

The user runs `alloy build`.  alloy-cli does:

1. Read `alloy.toml`:
   ```
   alloy        = ">=0.7,<0.8"
   alloy-codegen = ">=0.4,<0.5"
   alloy-devices-yml = ">=1.5,<1.6"
   ```
2. Read `.alloy/version.lock` (if present):
   ```
   alloy            = "0.7.3"
   alloy-codegen    = "0.4.1"
   alloy-devices-yml = "1.5.0"
   alloy-cli-pin    = "0.5.0"
   ```
3. Verify ranges contain locks.  If not, error with `alloy update`
   suggestion.
4. Verify resolved versions exist on disk.  If not, fetch:
   - alloy: from GitHub release tarball into `~/.alloy/sdk/<v>/`
   - alloy-codegen: `pip install alloy-codegen==<v>`
   - alloy-devices-yml: submodule `git checkout <sha-pin>` or pip
     `alloy-devices-yml-data==<v>`
5. Proceed with build.

This is the same dance Cargo does.  Reproducibility comes from the
lockfile.

## Network policy

- **Default**: alloy-cli may fetch when explicitly told (`alloy sdk
  install`, `alloy update`).
- **CI**: `--offline` flag forces local-only.  Lockfile must be
  satisfiable from cache.
- **Telemetry**: off by default, opt-in only.  Anonymous usage stats
  to a public endpoint, never PII / project content.

## Failure modes we explicitly handle

| Failure | Behaviour |
|---|---|
| `alloy-devices-yml` not initialised | clear error + `git submodule update --init` suggestion |
| Device not in admitted set | suggest closest device by name + list of admitted |
| Device in `bulk-admitted/` but not `vendors/` | offer to admit (writes a YAML to vendors/ via guided wizard, post-MVP) |
| `alloy-codegen` version mismatch | offer to install / upgrade |
| `alloy.toml` missing | suggest `alloy new` |
| `alloy.toml` invalid | print schema-validation error pointing at exact key |
| Toolchain missing | platform-specific install snippet (brew / apt / scoop) |
