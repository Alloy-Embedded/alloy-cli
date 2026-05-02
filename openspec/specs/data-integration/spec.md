# data-integration Specification

## Purpose
TBD - created by archiving change integrate-data-sources. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL load device IR from the alloy-devices-yml submodule

The `alloy_cli.core.ir` module SHALL load canonical device YAMLs
from `data/devices/vendors/<vendor>/<family>/devices/<device>.yml`
relative to the repo root.  It SHALL parse each YAML via
alloy-codegen's `canonical_device_yaml.parse_device` (re-exported,
not duplicated), MUST cache parsed results at
`.alloy/cache/ir/<vendor>_<family>_<device>.pkl` keyed by content
SHA plus `alloy-cli` version, and SHALL provide query helpers
(`connection_candidates`, `dma_routes`, `clock_nodes`,
`peripheral_clock_bindings`, `valid_pins_for`) that downstream
proposals consume.

#### Scenario: Loading an admitted device returns a typed IR

- **WHEN** `alloy_cli.core.ir.load_device("st", "stm32g0", "stm32g071rb")` is called
- **THEN** the returned object SHALL be a `CanonicalDeviceIR` instance
- **AND** the second call within the same process SHALL hit the
  on-disk pickle cache and return in under 10 ms

#### Scenario: Loading a missing device raises a clear error

- **WHEN** `load_device("st", "stm32x7", "stm32x7nope")` is called
  and the YAML does not exist
- **THEN** the call SHALL raise `DeviceNotFoundError`
- **AND** the error message SHALL include the searched path
  (`data/devices/vendors/st/stm32x7/devices/stm32x7nope.yml`) and
  a hint to run `alloy devices --search …`

### Requirement: alloy-cli SHALL detect required host toolchains

The `alloy_cli.core.toolchain` module SHALL report, for each known
toolchain name (`arm-none-eabi-gcc`, `clang+arm`,
`riscv64-unknown-elf-gcc`, `xtensa-esp32-elf-gcc`, `probe-rs`,
`openocd`, `jlink-gdb-server`), whether the binary is on `PATH`,
which version it reports, and per-OS install hints when missing.

#### Scenario: arm-gcc detected with version

- **WHEN** `arm-none-eabi-gcc 13.2.0` is on the user's `PATH`
- **AND** `core.toolchain.detect_arm_gcc()` is called
- **THEN** the result SHALL contain `present=True, version="13.2.0",
  path="/<resolved>/arm-none-eabi-gcc"`

#### Scenario: missing toolchain reports install hint

- **WHEN** `riscv64-unknown-elf-gcc` is not on PATH
- **AND** the host is macOS
- **THEN** `core.toolchain.detect_riscv_gcc()` SHALL return
  `present=False, install_hint="brew install riscv-elf-gcc"`

