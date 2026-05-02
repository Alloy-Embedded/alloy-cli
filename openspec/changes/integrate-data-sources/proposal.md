# Integrate Data Sources

## Why

`alloy-cli` reads from three sibling repos: `alloy-devices-yml` (canonical
IR), `alloy-codegen` (C++ emitter), `alloy` (HAL + boards).  Before any
command can do useful work, we need stable contracts for **how** those
sources are reached, **how** versions are pinned, and **how** the
caches invalidate.  See `docs/DATA_SOURCES.md` for the full mapping.

## What Changes

- **alloy-devices-yml access**: ship as git submodule at `data/devices/`
  matching the alloy-codegen pattern.  Optional fallback to a
  `alloy-devices-yml-data` PyPI package (post-MVP, behind
  `--data-source package`).
- **alloy-codegen access**: declared as a runtime dependency
  (`alloy-codegen>=0.4,<0.5`).  Invoked as a subprocess by default;
  `--codegen-mode inproc` enables in-process import.
- **alloy SDK access**: existing `alloy/tools/alloy-cli/sdk.py` logic
  ported into `src/alloy_cli/core/sdk.py`.  Cache directory:
  `${ALLOY_DEVICE_CACHE-~/.alloy/sdk/}/<version>/`.  Honours
  `ALLOY_OFFLINE=1`.
- **IR loader** (`src/alloy_cli/core/ir.py`): pure functions
  `load_device(vendor, family, device) -> DeviceIR`, with on-disk
  pickle cache keyed by content SHA + alloy-cli version.
- **Board catalog loader** (`src/alloy_cli/core/boards.py`): parses
  every `boards/<id>/board.json` from a configured alloy SDK
  checkout.
- **Toolchain detection** (`src/alloy_cli/core/toolchain.py`): port
  from `alloy/tools/alloy-cli/toolchains.py`, extended to detect
  arm-gcc / clang-arm / xtensa-esp / riscv64-elf-gcc / probe-rs.
- **Lockfile schema**: `.alloy/version.lock` records exact resolved
  versions of `alloy`, `alloy-codegen`, `alloy-devices-yml`,
  `alloy-cli`.
- **`alloy doctor` foundation**: a private `_diagnose()` function
  that drives Phase 5's `alloy doctor` command later.

## Impact

- `core.ir.load_device(...)` works end-to-end against the submodule.
- IR queries (`connection_candidates`, `dma_routes`, `clock_nodes`,
  …) are reachable from any `core/` consumer.
- Board catalog is loadable.
- Toolchain detection answers "is arm-gcc on PATH?" and similar.
- Establishes the v1 distribution choice (submodule) that downstream
  proposals depend on.

## What this DOES NOT do

- No CLI commands; everything is library-level.
- No version-resolution UI / `alloy update` flow (Phase 5).
- No bulk-admit support (post-MVP).
- No PyPI sidecar package; only submodule.
