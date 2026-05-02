# Tasks — integrate-data-sources

## Phase 1: alloy-devices-yml submodule

- [x] 1.1 `git submodule add https://github.com/Alloy-Embedded/alloy-devices-yml data/devices`
- [x] 1.2 `core.ir._DATA_DEVICES_ROOT = repo_root / "data" / "devices"`.
- [x] 1.3 `core.ir.discovered_device_registry()` walks
      `vendors/<v>/<f>/devices/*.yml`.

## Phase 2: IR loader

- [x] 2.1 `core.ir.load_device(vendor, family, device) -> DeviceIR`
      with PyYAML parsing and a typed projection.
- [x] 2.2 On-disk pickle cache at `.alloy/cache/ir/<v>_<f>_<d>.pkl`
      keyed by content SHA + `alloy_cli.__version__`.
- [x] 2.3 Public query helpers: `connection_candidates`,
      `dma_routes`, `peripherals_with_class`, `valid_pins_for`,
      `peripheral_names`.

## Phase 3: alloy SDK + board catalog

- [x] 3.1 `core.boards.BoardSummary` + `BoardManifest`
      dataclasses.
- [x] 3.2 `core.boards.load_catalog()` walks
      `${ALLOY_BOARDS_ROOT}/*/board.json`.  Empty catalogue when
      env var unset (the `add-cli-new` proposal wires the SDK
      download path).
- [x] 3.3 `core.boards.lookup(board_id)` returns the full manifest.

## Phase 4: Toolchain detection

- [x] 4.1 `core.toolchain.detect_*` for arm-gcc, riscv-gcc,
      xtensa-gcc, probe-rs, openocd, cmake, ninja.
- [x] 4.2 Per-OS install hint dict.
- [x] 4.3 `detect_all()` aggregator used by the future `alloy
      doctor`.

## Phase 5: Lockfile schema

- [x] 5.1 `core.lockfile.AlloyLockfile` dataclass.
- [x] 5.2 `read_lock(path)` and `write_lock(path, lock)` with
      deterministic serialisation.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/data-integration/spec.md`.
- [x] 6.2 `openspec validate integrate-data-sources --strict`
      passes.
- [x] 6.3 Tests: 19 cases across IR, toolchain, lockfile, boards
      (all green).
- [x] 6.4 Ruff + pyright clean.
