# `alloy.toml` — project format v1

`alloy-cli` projects are described by a single TOML file at the project
root: **`alloy.toml`**.  The file is the source of truth that every
command (`alloy build`, `alloy add`, `alloy flash`, the TUI, the MCP
server) reads and writes through `core.project`.

It is validated against
[`schema/alloy_toml_v1.json`](../schema/alloy_toml_v1.json) (JSON Schema
Draft 2020-12).  Read-time errors are surfaced with the offending JSON
path and the violated constraint.

## Skeleton

```toml
schema_version = "1.0.0"

[project]
name           = "blinky"
alloy-cli      = "0.5.0"          # optional, pinned by the lockfile too
alloy          = "0.7.3"
alloy-codegen  = "0.4.1"
alloy-devices-yml = "1.5.0"

# Either [board] OR [chip] — never both.
[board]
id = "stm32f4-discovery"

# [chip]
# vendor = "st"
# family = "stm32f4"
# device = "stm32f407vg"

[clocks]
profile = "max"

[[peripherals]]
kind  = "gpio"
name  = "led_green"
pin   = "PD12"
mode  = "output"
initial = 0

[[peripherals]]
kind  = "uart"
name  = "console"
peripheral = "USART2"
tx    = "PA2"
rx    = "PA3"
baud  = 115200

[build]
profile      = "release"          # debug | release | relwithdebinfo
optimization = "size"             # size | speed | debug
lto          = true

[flash]
probe          = "stlink"
openocd_config = "openocd/stm32f4-discovery.cfg"
```

## Top-level keys

| Key | Required | Notes |
|-----|----------|-------|
| `schema_version` | ✅ | `^1\.[0-9]+\.[0-9]+$`.  Major bumps are breaking. |
| `[project]` | ✅ | `name` is mandatory. |
| `[board]` | ❌ (one of) | Mutually exclusive with `[chip]`. |
| `[chip]` | ❌ (one of) | Mutually exclusive with `[board]`. |
| `[clocks]` | ❌ | Free-form; recognised keys: `profile`. |
| `[[peripherals]]` | ❌ | Each entry must have `kind` and `name`.  Per-kind sub-schemas validate the rest of the payload. |
| `[build]` | ❌ | `profile`, `optimization`, `lto` are recognised. |
| `[flash]` | ❌ | `probe`, `openocd_config` are recognised; vendors can extend. |

## Peripheral kinds

The schema enforces `kind ∈ { uart, gpio, spi, i2c, timer, pwm, adc,
dac, can, dma, rtc, watchdog, qspi, sdmmc, usb, eth }`.  Per-kind
required fields (today):

* `uart` — `peripheral`, `tx`, `rx`.
* `gpio` — `pin`, `mode ∈ {input, output, od, analog, alternate}`.
* `spi`  — `peripheral`, `sck`, `miso`, `mosi`.
* `i2c`  — `peripheral`, `sda`, `scl`.

Other kinds accept their `kind` + `name` and any extra keys; later
proposals will tighten their sub-schemas as the corresponding `alloy
add` commands land.

## Versioning

* `schema_version` is **always 3-segment SemVer**.
* `alloy-cli` only loads major version 1.
* Higher minor / patch versions on major 1 load successfully but do not
  promise feature-completeness on older tools.
* A higher major version (e.g. `2.0.0`) makes `read()` raise
  `ProjectConfigVersionError` with a "run `alloy update`" message.

## `.alloy/` cache layout

`alloy-cli` keeps everything generated or cached out of source control
under `.alloy/`:

```
.alloy/
├── version.lock        # exact pins of alloy/alloy-codegen/etc
├── cache/              # IR pickles, parser caches
└── generated/          # codegen output (alloy-codegen later)
```

`core.project.AlloyDir(repo_root)` resolves these paths.  `ensure()`
creates the directory layout idempotently.

## CMake integration

A project's `CMakeLists.txt` reads `alloy.toml` through the bundled
helper:

```cmake
find_package(Python3 REQUIRED COMPONENTS Interpreter)
include(${ALLOY_CLI_CMAKE_DIR}/AlloyCli.cmake)
alloy_cli_init()

add_executable(${ALLOY_PROJECT_NAME} src/main.c)
alloy_cli_link(${ALLOY_PROJECT_NAME})
```

The helper invokes `python -m alloy_cli.cmake_bridge --emit-json` and
reads the manifest with CMake's built-in JSON parser — keeping CMake
out of TOML parsing entirely.

## Migration

Future schema versions add a `migrate(toml_text, from_version,
to_version)` helper in `core.project`.  The current major (1) has no
migrations to apply yet.
