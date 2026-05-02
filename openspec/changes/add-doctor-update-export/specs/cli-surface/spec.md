## ADDED Requirements

### Requirement: alloy-cli SHALL diagnose the host environment via `alloy doctor`

The `alloy doctor` command SHALL aggregate checks across Python
runtime, toolchains, probes, project validity, network, and
alloy component versions.  It SHALL emit a Rich-formatted human
report by default and JSON via `--json`.  It SHALL offer
auto-fixers for safe issues (pip-install missing deps, init
submodule); it SHALL NEVER auto-install system toolchains, only
print the install command.

#### Scenario: doctor reports a missing toolchain with install hint

- **WHEN** `arm-none-eabi-gcc` is not on `PATH`
- **AND** the user runs `alloy doctor`
- **THEN** the report SHALL flag `arm-none-eabi-gcc` as missing
- **AND** SHALL include the OS-specific install command
- **AND** SHALL exit non-zero (signals a remediable issue)

### Requirement: alloy-cli SHALL atomically upgrade ecosystem components via `alloy update`

The `alloy update` command SHALL resolve and apply upgrades for
`alloy`, `alloy-codegen`, `alloy-devices-yml`, and `alloy-cli`
itself.  It SHALL operate atomically: if any component upgrade
fails, the lockfile SHALL NOT be modified.  `--dry-run` SHALL
preview without applying; `--frozen` SHALL refuse any change.

#### Scenario: dry-run lists pending upgrades

- **WHEN** `alloy 0.7.5` is available and the lockfile pins
  `alloy 0.7.3`
- **AND** the user runs `alloy update --dry-run`
- **THEN** the output SHALL list `alloy 0.7.3 → 0.7.5`
- **AND** the lockfile SHALL NOT be modified

### Requirement: alloy-cli SHALL emit auxiliary configurations via `alloy export`

The `alloy export <kind>` command SHALL generate
project-specific configuration files for CI (`github`, `gitlab`,
`jenkins`), VS Code (`launch.json`, `tasks.json`,
`c_cpp_properties.json`), GDB (`.gdbinit`), and BOM (chip + any
declared external components).

#### Scenario: alloy export vscode produces a valid launch config

- **WHEN** the user runs `alloy export vscode` inside a
  configured project
- **THEN** `.vscode/launch.json` SHALL be created with a
  `cortex-debug` configuration referencing the project's `.elf`
  output and the project's selected probe
- **AND** `.vscode/tasks.json` SHALL contain `build`, `flash`,
  `debug` tasks invoking `alloy build`, `alloy flash`,
  `alloy debug`
