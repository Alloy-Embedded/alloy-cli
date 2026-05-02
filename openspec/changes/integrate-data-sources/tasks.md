# Tasks — integrate-data-sources

## Phase 1: alloy-devices-yml submodule

- [ ] 1.1 `git submodule add https://github.com/Alloy-Embedded/alloy-devices-yml data/devices`
- [ ] 1.2 `core.ir._DATA_DEVICES_ROOT = repo_root / "data" / "devices"`
- [ ] 1.3 Mirror alloy-codegen's `bootstrap._discover_device_registry`
      into `core.ir.discovered_device_registry()`.

## Phase 2: IR loader

- [ ] 2.1 `core.ir.load_device(vendor, family, device) -> DeviceIR`
      using the alloy-codegen `canonical_device_yaml.parse_device`
      helper (re-export, don't duplicate).
- [ ] 2.2 On-disk pickle cache at `.alloy/cache/ir/<v>_<f>_<d>.pkl`
      keyed by content SHA + `alloy-cli.__version__`.
- [ ] 2.3 Public query helpers:
      `connection_candidates(device, peripheral, signal)`,
      `dma_routes(device, peripheral, direction)`,
      `clock_nodes(device)`, `peripheral_clock_bindings(device)`,
      `valid_pins_for(device, signal)`.

## Phase 3: alloy SDK + board catalog

- [ ] 3.1 Port `alloy/tools/alloy-cli/sdk.py` into
      `src/alloy_cli/core/sdk.py` (download, cache, version pinning).
- [ ] 3.2 Port `alloy/tools/alloy-cli/_boards.toml` semantics into
      `core.boards.load_catalog(sdk_root) -> tuple[BoardSummary,
      ...]` reading `<sdk>/boards/*/board.json`.
- [ ] 3.3 `core.boards.lookup(board_id)` returns the full
      `BoardManifest` dataclass.

## Phase 4: Toolchain detection

- [ ] 4.1 Port `alloy/tools/alloy-cli/toolchains.py` into
      `src/alloy_cli/core/toolchain.py`.
- [ ] 4.2 Extend detection: arm-none-eabi-gcc, clang+arm,
      riscv64-unknown-elf-gcc, xtensa-esp32-elf-gcc, probe-rs,
      openocd, jlink-gdb-server.
- [ ] 4.3 Per-OS install hint dict (mac / linux / win) used later by
      `alloy doctor`.

## Phase 5: Lockfile schema

- [ ] 5.1 `core.lockfile.AlloyLockfile` dataclass (alloy,
      alloy-codegen, alloy-devices-yml, alloy-cli versions).
- [ ] 5.2 `read_lock(.alloy/version.lock) -> AlloyLockfile`,
      `write_lock(...)`, `verify(versions, ranges) -> Diagnostic`.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/data-integration/spec.md`.
- [ ] 6.2 `openspec validate integrate-data-sources --strict` passes.
- [ ] 6.3 Unit tests for IR loader (load 3 devices, ensure cache hit
      on second call).
- [ ] 6.4 Unit tests for board catalog (fixture SDK root with 2
      boards).
