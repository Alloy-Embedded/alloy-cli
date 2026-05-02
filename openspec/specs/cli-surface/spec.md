# cli-surface Specification

## Purpose
TBD - created by archiving change bootstrap-alloy-cli. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL ship as a pip-installable package with an `alloy` entry point

The `alloy-cli` distribution SHALL be installable via `pip install
alloy-cli`, MUST register a console script entry named `alloy`
mapped to `alloy_cli.main:main`, and SHALL be compatible with
Python 3.11, 3.12, and 3.13.

#### Scenario: pip install registers the alloy command

- **WHEN** a user runs `pip install alloy-cli` in a virtualenv on
  Python 3.11+
- **THEN** the `alloy` command SHALL be on `PATH`
- **AND** running `alloy --version` SHALL exit 0 and print a
  non-empty SemVer version string sourced from VCS tags

#### Scenario: --help describes the tool

- **WHEN** the user runs `alloy --help`
- **THEN** the output SHALL exit 0
- **AND** SHALL include the string "Alloy embedded platform"
- **AND** SHALL list available subcommands (initially empty placeholder list)

#### Scenario: license is dual MIT or Apache-2.0

- **WHEN** the package metadata is inspected via
  `pip show alloy-cli`
- **THEN** the `License` field SHALL read "MIT OR Apache-2.0"
- **AND** both `LICENSE-MIT` and `LICENSE-APACHE` SHALL be
  distributed alongside the wheel

### Requirement: alloy-cli SHALL scaffold projects via `alloy new`

The `alloy new <NAME>` command SHALL produce a complete,
schema-valid alloy project tree from either a `--board <id>` or a
`--device <vendor>/<family>/<chip>` argument.  The generated tree
SHALL include: `alloy.toml`, `CMakeLists.txt`, `src/main.cpp`,
`README.md`, `.gitignore`, and SHALL pre-populate the manifest
with sensible defaults from the chosen board (debug UART, default
clock profile, LED GPIO when available).  The command SHALL refuse
to scaffold into a non-empty directory unless `--force` is given.

#### Scenario: alloy new --board nucleo_g071rb produces a buildable project

- **WHEN** the user runs `alloy new firmware --board nucleo_g071rb`
  in an empty directory
- **THEN** a directory `firmware/` SHALL be created
- **AND** `firmware/alloy.toml` SHALL validate against
  `schema/alloy_toml_v1.json`
- **AND** `firmware/alloy.toml [board].id` SHALL be
  `"nucleo_g071rb"`
- **AND** running `cmake -S firmware -B firmware/build` SHALL exit 0

#### Scenario: alloy new without board or device fails clearly

- **WHEN** the user runs `alloy new firmware` with neither `--board`
  nor `--device`
- **THEN** the command SHALL exit non-zero
- **AND** stderr SHALL list `alloy boards` and `alloy devices` as
  next-step suggestions

#### Scenario: alloy new refuses non-empty target

- **WHEN** the user runs `alloy new firmware --board <id>` and
  `firmware/` already contains any file
- **AND** `--force` is **not** specified
- **THEN** the command SHALL exit non-zero with a message naming
  the existing files

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

### Requirement: alloy-cli SHALL list and search boards and devices

The `alloy boards` and `alloy devices` commands SHALL surface the
catalogues backed by `alloy/boards/*/board.json` and
`alloy-devices-yml` respectively.  Both SHALL support free-text
search (matching board_id / mcu / vendor / family / device-name),
faceted filters (vendor, ISA, has-feature, tier), JSON output for
scripting, and a positional detail mode (`alloy boards <id>`,
`alloy devices <name>`).

#### Scenario: alloy boards lists all admitted boards

- **WHEN** the user runs `alloy boards`
- **THEN** the command SHALL exit 0
- **AND** SHALL list every board found in the resolved alloy SDK
  catalogue (currently 11+)
- **AND** the output SHALL include columns for board_id, mcu,
  vendor, family, ISA, tier

#### Scenario: alloy boards --search filters by query

- **WHEN** the user runs `alloy boards --search nucleo`
- **THEN** the result SHALL contain only boards whose board_id /
  mcu / vendor matches `nucleo` (fuzzy)
- **AND** results SHALL be ranked by best match first

#### Scenario: alloy boards --json emits stable schema

- **WHEN** the user runs `alloy boards --json`
- **THEN** stdout SHALL be a single JSON document with shape
  `{"schema_version":"1.0", "boards":[BoardSummary...]}`
- **AND** each `BoardSummary` SHALL contain `board_id`, `mcu`,
  `vendor`, `family`, `core`, `flash_size_bytes`,
  `clock_profiles`, `tier`

#### Scenario: alloy devices --all includes bulk-admitted chips

- **WHEN** the user runs `alloy devices --all --vendor st`
- **THEN** the result SHALL include both `vendors/st/...` and
  `bulk-admitted/.../st/...` devices
- **AND** results SHALL be tagged `admitted=true|false`

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

### Requirement: alloy update SHALL actually upgrade pip + submodule components

`alloy update` SHALL invoke real upgraders for each pinned
component (`alloy-devices-yml` via git submodule, `alloy-codegen`
/ `alloy` / `alloy-cli` via pip).  Upgraders SHALL run in
dependency order — devices → codegen → alloy → alloy-cli — and
the lockfile SHALL be rewritten only when every step succeeds.
Any non-zero return code SHALL abort the sequence and leave the
lockfile bytes unchanged.

#### Scenario: alloy update upgrades pip packages and rewrites the lockfile

- **WHEN** `alloy.toml` pins `alloy = "0.7.5"` and
  `.alloy/version.lock` records `alloy = "0.7.3"`
- **AND** the user runs `alloy update`
- **THEN** the command SHALL invoke
  `python -m pip install --upgrade alloy==0.7.5` exactly once
- **AND** the lockfile SHALL be rewritten with `alloy = "0.7.5"`
- **AND** the success summary SHALL list the upgraded component
  per row

#### Scenario: a failing upgrader leaves the lockfile untouched

- **WHEN** `alloy update` is running and the alloy-codegen pip
  install exits non-zero
- **THEN** the command SHALL exit non-zero
- **AND** the lockfile bytes on disk SHALL be byte-identical to
  the pre-update state
- **AND** the failure summary SHALL name the failing component
  and surface the captured stderr tail

#### Scenario: upgrading alloy-cli reminds the user to restart the process

- **WHEN** `alloy-cli` itself is among the upgraded components
- **THEN** the upgrade summary SHALL include a reminder to
  re-launch `alloy` so the new version is on PATH
- **AND** the lockfile SHALL still be rewritten before the
  reminder prints

### Requirement: alloy doctor SHALL support a non-interactive `--fix` mode

`alloy doctor --fix` SHALL iterate over every check whose
`CheckResult.auto_fix` is non-None and run the registered fixer
through `core.process.runner`.  The command SHALL exit 0 iff
every error-severity row passes after the fixers run; otherwise
SHALL exit 1 with a per-check status summary.

#### Scenario: --fix initialises the alloy-devices-yml submodule

- **WHEN** the alloy-devices-yml submodule is uninitialised
- **AND** the user runs `alloy doctor --fix`
- **THEN** the command SHALL invoke
  `git submodule update --init` exactly once
- **AND** the command SHALL exit 0 if the post-fix re-run shows
  every check passing

#### Scenario: --fix surfaces a failing fixer with non-zero exit

- **WHEN** an auto-fix returns `ok=False`
- **AND** the underlying check is error-severity
- **THEN** the command SHALL exit 1
- **AND** the summary SHALL include the captured stderr tail and
  the unchanged install hint

### Requirement: All façades SHALL render typed errors via the AlloyCliError contract

Every code path under `src/alloy_cli/` SHALL replace bare
`except Exception` catches with a narrow exception list whose
recoverable cases are rethrown as a subclass of
`alloy_cli.core.errors.AlloyCliError`.  The CLI Click runner,
the Textual app, and the MCP tool registry SHALL each render
those typed errors with their stable `error_type` so users see
actionable messages instead of generic "something went wrong"
text.  Suppressed exceptions (the few legitimate cases where
re-raising would crash the TUI) SHALL be routed through
`core.log.get_logger(...)` so a maintainer can grep
`.alloy/cache/alloy-cli.log` after the fact.

#### Scenario: an uninitialised submodule surfaces a structured diagnostic

- **WHEN** the user runs `alloy add uart console` in a checkout
  whose `data/devices/` submodule is missing
- **THEN** the CLI SHALL exit with the stable code mapped from
  `DataRepoMissingError`
- **AND** the printed message SHALL include the
  `git submodule update --init` install hint

#### Scenario: TUI peripheral-add surfaces the typed error in a notification

- **WHEN** the user opens the peripheral-add screen against a
  board whose chip YAML is missing
- **THEN** the screen SHALL emit a `notify(severity="error")`
  whose body matches the `DeviceNotFoundError.error_type`
- **AND** a corresponding `ERROR` line SHALL land in
  `.alloy/cache/alloy-cli.log`

#### Scenario: ruff BLE001 lint stays green

- **WHEN** CI runs `ruff check src tests` with `BLE001`
  enabled
- **THEN** the run SHALL exit zero
- **AND** no `# noqa: BLE001` markers SHALL be required

### Requirement: Structured log is rotation-bounded and tmp-overridable

`core.log.get_logger(name)` SHALL append to
`.alloy/cache/alloy-cli.log` by default and SHALL roll once the
file passes 1 MB, retaining a single `.1` backup.  The
`ALLOY_CLI_LOG` environment variable SHALL override the file
path so the test suite can pin it to a tmp directory.

#### Scenario: log rotates after 1 MB

- **WHEN** `.alloy/cache/alloy-cli.log` already weighs 1 MB and
  another log line is emitted
- **THEN** the existing file SHALL be renamed to
  `alloy-cli.log.1`
- **AND** the new line SHALL land in a freshly-opened
  `alloy-cli.log` whose size is below 1 MB

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

