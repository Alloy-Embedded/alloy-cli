## ADDED Requirements

### Requirement: alloy export ci SHALL emit a self-contained, matrix-aware GitHub Actions workflow

`alloy export ci` SHALL write a workflow YAML that installs the
chip's cross-compile toolchain (arm-none-eabi-gcc /
riscv-gnu-toolchain / xtensa-esp32-elf) before invoking
`alloy build`.  The workflow SHALL run a `profile ∈
{debug, release}` matrix, cache pip + alloy-devices-yml on the
SHA of `alloy.toml + version.lock`, and upload the produced
ELF + map file as artifacts.  A failing job SHALL run
`alloy doctor --json` so the captured log surfaces actionable
install hints.

#### Scenario: STM32 chip target gets arm-none-eabi-gcc installed

- **WHEN** the project's `[chip]` is `st/stm32g0/stm32g071rb`
- **AND** the user runs `alloy export ci`
- **THEN** the emitted `.github/workflows/firmware.yml` SHALL
  reference `carlosperate/arm-none-eabi-gcc-action`
- **AND** SHALL declare a matrix with at least the values
  `debug` and `release` for `profile`

#### Scenario: RP2040 RISC-V target swaps to riscv-gnu-toolchain

- **WHEN** the project's `[chip]` is `rp/rp2350/rp2350a` (a
  RISC-V core variant)
- **AND** the user runs `alloy export ci`
- **THEN** the emitted YAML SHALL install the RISC-V GCC
  toolchain via the appropriate action
- **AND** SHALL NOT install arm-none-eabi-gcc

#### Scenario: failing build runs alloy doctor for diagnostics

- **WHEN** the emitted workflow runs and `alloy build` exits
  non-zero
- **THEN** a subsequent step gated on `if: failure()` SHALL
  execute `alloy doctor --json`
- **AND** the doctor output SHALL appear in the job log so
  the maintainer can see which dependency went missing

#### Scenario: --dry-run prints the YAML without touching disk

- **WHEN** the user runs `alloy export ci --dry-run`
- **THEN** the YAML SHALL print to stdout
- **AND** `.github/workflows/firmware.yml` SHALL NOT be
  created or modified
