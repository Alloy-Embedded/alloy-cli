# Wire the Alloy HAL Into Scaffolded Projects via FetchContent

## Why

Today `alloy new` writes a `CMakeLists.txt` that:

1. Calls `alloy_cli_init()` — parses `alloy.toml` ✓
2. Calls `add_executable(... src/main.cpp)` — declares the binary ✓
3. Calls `alloy_cli_link(target)` — adds `.alloy/generated/include`
   to the include path ✓

…and **never pulls the alloy HAL itself**.  The scaffolded
`src/main.cpp` `#include "alloy/board/board.hpp"` fails because
the HAL is nowhere on the include path.  No `find_package(alloy)`,
no `FetchContent_Declare(alloy)`, no path override — just a
broken build.

Now that alloy's CMake package is FetchContent-friendly
(`alloy/openspec/changes/archive/2026-05-02-add-fetchcontent-
helpers-loading/`), the scaffold can pull the HAL in directly
and call the canonical `alloy_add_runtime_executable(...)` helper.

## What Changes

### Template

- `CMakeLists.txt.j2` is rewritten to:
  - `include(FetchContent)`.
  - `FetchContent_Declare(alloy GIT_REPOSITORY ... GIT_TAG ...)`,
    pinned via `alloy.toml [project].alloy` (already exposed as
    the `ALLOY_PROJECT_ALLOY` CMake variable).  The default
    repository URL is the public alloy GitHub.
  - Local-checkout override via `-DALLOY_SOURCE_OVERRIDE=/path`
    so contributors developing the HAL in parallel don't hit
    the network.
  - `set(ALLOY_BOARD "${ALLOY_BOARD_ID}" CACHE STRING "" FORCE)`
    before `FetchContent_MakeAvailable(alloy)` so alloy's
    board-driven configure picks the right platform / linker.
  - `alloy_add_runtime_executable(${ALLOY_PROJECT_NAME} SOURCES
    src/main.cpp)` to link `Alloy::hal` + the board's startup
    + linker script.
  - `alloy_cli_link(${ALLOY_PROJECT_NAME})` keeps adding the
    codegen include path on top.

### `AlloyCli.cmake`

- `alloy_cli_link(target)` becomes a no-op when `Alloy::hal`
  isn't a target (so projects that don't use FetchContent
  still configure without erroring) — but warns once.
- A new `alloy_cli_resolve_alloy_tag()` helper gives the
  template a single source for "what GIT_TAG should we pin".

### Chip-only projects

- Projects with `[chip]` instead of `[board]` get a comment in
  the generated CMakeLists pointing them at a follow-up
  proposal; scaffold raises a clear error today instead of
  silently producing an unbuildable tree.

### Example refresh

- The four `docs/EXAMPLES/*` projects are validated by the
  existing snapshot tests — no template-level smoke needed.
- A new test
  `tests/test_scaffold_cmake_template.py` confirms the
  emitted CMakeLists references `FetchContent_Declare(alloy`
  and `alloy_add_runtime_executable(`.

## Impact

- A user who runs `alloy new myproj --board nucleo_g071rb;
  cd myproj; cmake -S . -B build -DALLOY_BOARD=nucleo_g071rb`
  gets a configure pass that pulls the HAL, links it, and
  produces a buildable ELF.
- The "alloy-codegen-not-installed → skipped" path remains
  the safety net; once `pip install alloy-codegen` is in the
  user's env (which now actually exposes a `generate(...)`
  callable thanks to the alloy-codegen #1 proposal), the
  build pipeline runs end-to-end.

## What this DOES NOT do

- Does not download the HAL at `alloy new` time (only at
  `cmake` time, like every other FetchContent dep).
- Does not introduce chip-only board manifests; the helper
  still expects an `ALLOY_BOARD` cache var (board-driven
  projects).  Chip-only support is its own proposal.
- Does not change `alloy.toml` schema — `[project].alloy`
  remains a free-form version pin.
