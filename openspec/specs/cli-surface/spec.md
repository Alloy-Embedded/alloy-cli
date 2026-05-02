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

