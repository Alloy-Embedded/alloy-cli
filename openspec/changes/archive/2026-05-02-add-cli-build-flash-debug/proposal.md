# Add `alloy build` / `flash` / `debug` Commands

## Why

Once a project exists, the daily-driver verbs are build, flash, and
debug.  Today every embedded toolchain forces the user to invoke
`cmake / ninja` then a per-vendor flasher then GDB by hand.
`alloy-cli` collapses all three into one tool with toolchain +
probe auto-detection.

Three commands ship together because they share the same
infrastructure: probe-rs / OpenOCD detection, CMake invocation,
linker map parsing for the memory summary.

## What Changes

### `alloy build [--profile debug|release|relwithdebinfo] [--clean]`

- Reads `alloy.toml` → resolves device → invokes `alloy-codegen
  generate` if generated headers are stale.
- Auto-detects toolchain via `core.toolchain.detect_*`; errors with
  install hint when missing.
- Runs `cmake -S . -B .alloy/build -G Ninja
  -DCMAKE_BUILD_TYPE=<profile>` then `cmake --build .alloy/build`.
- Streams output via Rich; collapses cmake configure noise.
- After success: prints memory summary (flash / RAM usage from the
  `.elf` file) computed in `core.memory`.

### `alloy flash [--probe auto|jlink|stlink|picoprobe|cmsis-dap]
                  [--target <name>]`

- Resolves elf path from last build (or rebuilds if missing).
- Auto-detects connected probes via `probe-rs list`.
- Calls `probe-rs run <elf>` (preferred) or `openocd` fallback.
- Live progress via `core.flash.run_with_progress(...)`.

### `alloy debug [--probe ...] [--gdb-ui auto|tui|gef|none]`

- Spawns `probe-rs gdb` (or OpenOCD `gdb-server`) in the
  background, then launches the configured GDB front-end attached
  to it.
- On `Ctrl+C` cleans up both processes.

## Impact

Phase 2 closes the **build → flash → debug** loop in three commands.
Combined with `alloy new` and the (next) `alloy add`, the user has a
fully scriptable firmware workflow without ever opening a vendor
IDE.

## What this DOES NOT do

- No live build log TUI screen (Phase 3 — `add-tui-clock-tree-and-build-flash`).
- No GDB front-end ships with alloy-cli — we wrap the user's
  configured GDB / GDB TUI / GEF / gdb-dashboard.
- No remote target (e.g., flashing over network) — local probe
  only.
- No multi-target build orchestration — single project, single
  binary.
