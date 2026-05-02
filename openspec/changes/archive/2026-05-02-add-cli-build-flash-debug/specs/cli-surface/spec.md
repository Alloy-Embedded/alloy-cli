## ADDED Requirements

### Requirement: alloy-cli SHALL build, flash, and debug projects with one command each

`alloy build`, `alloy flash`, and `alloy debug` SHALL be the
single user-facing verbs for those operations.  Each SHALL detect
required toolchains and probes automatically; SHALL surface an
actionable install hint when a dependency is missing; SHALL stream
live progress; and SHALL never require the user to invoke `cmake`,
`ninja`, `probe-rs`, or `gdb` directly for the common path.

#### Scenario: alloy build succeeds when arm-gcc is present

- **WHEN** the user runs `alloy build` inside a project scaffolded
  for `nucleo_g071rb`
- **AND** `arm-none-eabi-gcc` is on the user's `PATH`
- **THEN** the command SHALL exit 0
- **AND** SHALL produce `.alloy/build/<project>.elf`
- **AND** SHALL print a memory summary (flash / RAM usage) for the
  produced ELF

#### Scenario: alloy build with missing toolchain prints install hint

- **WHEN** `arm-none-eabi-gcc` is not on `PATH`
- **AND** the user runs `alloy build` on a Cortex-M project
- **THEN** the command SHALL exit non-zero
- **AND** stderr SHALL include the OS-specific install command
  (e.g., `brew install arm-none-eabi-gcc` on macOS)
- **AND** SHALL hint at `alloy doctor` for full diagnostics

#### Scenario: alloy flash auto-selects the connected probe

- **WHEN** exactly one J-Link probe is connected via USB
- **AND** the user runs `alloy flash`
- **THEN** the command SHALL select the J-Link without prompting
- **AND** SHALL stream progress to the terminal
- **AND** SHALL exit 0 on successful flash + verify

#### Scenario: alloy flash with multiple probes prompts a choice

- **WHEN** two probes are connected (J-Link and ST-Link)
- **AND** the user runs `alloy flash` (no `--probe` argument)
- **THEN** the command SHALL list the two probes with serials
- **AND** SHALL prompt the user to pick one (or accept `--probe`
  on the next invocation)

#### Scenario: alloy debug spawns server + GDB front-end

- **WHEN** the user runs `alloy debug` with a connected probe
- **THEN** a probe-rs gdb-server SHALL be launched in the
  background
- **AND** the user's configured GDB front-end SHALL attach
- **AND** on `Ctrl+C` both processes SHALL be cleaned up
