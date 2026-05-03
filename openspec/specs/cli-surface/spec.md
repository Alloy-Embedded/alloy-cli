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

The ``alloy new <NAME>`` command SHALL produce a complete,
schema-valid alloy project tree from either a ``--board <id>`` or a
``--device <vendor>/<family>/<chip>`` argument.  The generated tree
SHALL include: ``alloy.toml``, ``CMakeLists.txt``, ``src/main.cpp``,
``README.md``, ``.gitignore``, and SHALL pre-populate the manifest
with sensible defaults from the chosen board (debug UART, default
clock profile, LED GPIO when available).  The command SHALL refuse
to scaffold into a non-empty directory unless ``--force`` is given.

After scaffolding completes, ``alloy new`` SHALL offer to install
the family's toolchain.  The decision is governed by:

- ``--install-toolchain`` — always install; overrides every
  default.
- ``--no-install-toolchain`` — never install; overrides every
  default.
- ``--auto`` — combine with the install path; suppress every
  interactive confirmation.
- Default behaviour: when STDIN is a TTY and no flag was given,
  print the install plan and prompt ``Install toolchain now?
  [Y/n]``.  When STDIN is non-TTY (CI / pipe) and no flag was
  given, skip the install.

In every code path — installed, skipped, declined — the
post-scaffold output SHALL include the next-step commands the
user should run, including the explicit
``alloy toolchain install`` reminder when the install was
skipped.

#### Scenario: alloy new --board nucleo_g071rb produces a buildable project

- **WHEN** the user runs ``alloy new firmware --board nucleo_g071rb``
  in an empty directory with STDIN non-TTY
- **THEN** a directory ``firmware/`` SHALL be created
- **AND** ``firmware/alloy.toml`` SHALL validate against
  ``schema/alloy_toml_v1_1.json``
- **AND** ``firmware/alloy.toml [board].id`` SHALL be
  ``"nucleo_g071rb"``
- **AND** running ``cmake -S firmware -B firmware/build`` SHALL exit 0

#### Scenario: alloy new without board or device fails clearly

- **WHEN** the user runs ``alloy new firmware`` with neither
  ``--board`` nor ``--device``
- **THEN** the command SHALL exit non-zero
- **AND** stderr SHALL list ``alloy boards`` and ``alloy devices`` as
  next-step suggestions

#### Scenario: alloy new refuses non-empty target

- **WHEN** the user runs ``alloy new firmware --board <id>`` and
  ``firmware/`` already contains any file
- **AND** ``--force`` is **not** specified
- **THEN** the command SHALL exit non-zero with a message naming
  the existing files

#### Scenario: --install-toolchain triggers post-scaffold install

- **WHEN** the user runs
  ``alloy new firmware --board nucleo_g071rb --install-toolchain
  --auto``
- **THEN** ``firmware/.alloy/toolchain.lock`` SHALL exist after
  the run
- **AND** the install plan SHALL be printed before the install
- **AND** every required non-vendor tool from stm32g0 SHALL be
  in the toolchain store
- **AND** vendor tools SHALL be skipped with their install_doc URL

#### Scenario: --no-install-toolchain skips the post-scaffold install

- **WHEN** the user runs
  ``alloy new firmware --board nucleo_g071rb --no-install-toolchain``
- **THEN** no toolchain install SHALL run
- **AND** ``firmware/.alloy/toolchain.lock`` SHALL NOT exist
- **AND** the output SHALL include
  ``Run `alloy toolchain install`` as the next step

#### Scenario: TTY default offers the prompt and respects N

- **WHEN** the user runs
  ``alloy new firmware --board nucleo_g071rb`` in a TTY
- **AND** answers ``n`` to the install prompt
- **THEN** no install SHALL run
- **AND** the next-step command SHALL be printed

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

``alloy doctor --fix`` SHALL run every available auto-fixer in
sequence and report a summary of outcomes.  The fix surface SHALL
include:

- ``alloy-devices-yml`` — git submodule init.
- ``mcp`` — pip install ``alloy-cli[mcp]``.
- ``toolchain:<tool-name>`` — install a missing non-vendor
  toolchain entry through
  ``toolchain_orchestrator.install_family`` (Wave 3).  One
  synthetic fixer per missing required tool the family declares.

Vendor-source tools SHALL NEVER be auto-fixed; they remain
info-severity rows with their per-OS install_doc URL.  A failure
in one fixer SHALL NOT abort the others — every queued fixer
runs.  The ``_print_fix_summary`` table SHALL surface per-tool
outcomes (✓ installed / ✗ failed / dim "skipped — vendor"
rows).  The exit code SHALL be 0 when no error rows remain in
the post-fix re-scan, and 1 otherwise.

The behaviour SHALL be additive: a project without a resolvable
family keeps today's two-fixer surface.  Adding the toolchain
fixer never blocks the existing ``--fix`` path.

#### Scenario: doctor --fix installs missing required tools for stm32g0

- **WHEN** the user runs ``alloy doctor --fix`` in a stm32g0
  project where arm-none-eabi-gcc, cmake, ninja, probe-rs are all
  missing
- **AND** the toolchain store starts empty
- **THEN** the four required tools SHALL be installed in sequence
- **AND** ``.alloy/toolchain.lock`` SHALL pin all four
- **AND** STM32CubeProgrammer (recommended, vendor) SHALL render
  as info — never as a failure, never as an attempted install

#### Scenario: doctor --fix reports per-tool failures without aborting

- **WHEN** ``alloy doctor --fix`` is run and the second tool's
  install raises ``family-toolchain-installer-checksum``
- **THEN** the first tool's outcome SHALL be ``installed``
- **AND** the second tool's outcome SHALL be ``failed`` with
  the typed error_type
- **AND** the third tool SHALL still be attempted

#### Scenario: doctor --fix without a resolvable family preserves today's behaviour

- **WHEN** ``alloy doctor --fix`` is run outside any project AND
  without ``--for``
- **THEN** the legacy fixers (submodule init, MCP install) SHALL
  still run
- **AND** no toolchain auto-fix SHALL be queued
- **AND** the output SHALL match the pre-Wave-3 baseline

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

### Requirement: alloy debug SHALL launch a Textual front-end by default and fall back to the wrapper on demand

`alloy debug` SHALL detect a TTY and, when present, launch
`tui.screens.DebugScreen` against a `core.gdb.GdbSession`
attached to a freshly-spawned `probe-rs gdb-server`.  The
existing wrapper behaviour (spawn server + launch the user's
configured GDB front-end) SHALL remain accessible via
`--no-tui`.  Multi-probe disambiguation SHALL reuse
`core.flash.detect_probes` so the user picks once.

#### Scenario: alloy debug on a TTY opens the DebugScreen

- **WHEN** the user runs `alloy debug` on a TTY with a
  single probe attached
- **THEN** the CLI SHALL spawn `probe-rs gdb-server` on a
  fresh port
- **AND** SHALL push `tui.screens.DebugScreen` connected to
  that server
- **AND** SHALL NOT launch a separate GDB front-end

#### Scenario: --no-tui keeps the wrapper

- **WHEN** the user runs `alloy debug --no-tui`
- **THEN** the CLI SHALL spawn `probe-rs gdb-server` AND
  the user's configured GDB front-end (env var
  `ALLOY_GDB` or the default
  `arm-none-eabi-gdb`)
- **AND** the Textual screen SHALL NOT be launched

#### Scenario: --port overrides the gdb-server port

- **WHEN** the user runs `alloy debug --port 4321`
- **THEN** the spawned gdb-server SHALL bind to port 4321
- **AND** the DebugScreen SHALL connect to that port

### Requirement: Scaffolded CMakeLists SHALL FetchContent the alloy HAL by default

The CMakeLists template emitted by `alloy new` SHALL pull the
alloy C++ HAL via `FetchContent_Declare(alloy ...)` and call
the HAL's `alloy_add_runtime_executable(...)` helper to link
the produced binary against `Alloy::hal`.  The version pinned
in `alloy.toml [project].alloy` SHALL flow through to the
HAL's GIT_TAG; missing pins fall back to `main`.  A
`-DALLOY_SOURCE_OVERRIDE=<path>` cache variable SHALL bypass
the git fetch and consume a local HAL checkout, so contributors
working on the HAL alongside a downstream project don't pay the
network round-trip.

#### Scenario: a board-driven project configures with the HAL pulled in

- **WHEN** the user runs `alloy new myproj --board
  nucleo_g071rb` and the resulting `CMakeLists.txt` is read
- **THEN** the file SHALL contain
  `FetchContent_Declare(alloy` and
  `alloy_add_runtime_executable(`
- **AND** SHALL `set(ALLOY_BOARD "${ALLOY_BOARD_ID}" CACHE
  STRING "" FORCE)` before `FetchContent_MakeAvailable(alloy)`
  so alloy resolves the platform / linker for the board

#### Scenario: a chip-only project errors with a clear message

- **WHEN** the user runs `alloy new chipproj --device
  st/stm32g0/stm32g071rb`
- **THEN** the scaffold SHALL exit non-zero with a message
  pointing at the chip-only-board follow-up proposal
- **AND** SHALL NOT leave a half-written project tree on disk

#### Scenario: ALLOY_SOURCE_OVERRIDE bypasses the git fetch

- **WHEN** the user runs `cmake -S . -B build
  -DALLOY_SOURCE_OVERRIDE=/path/to/alloy
  -DALLOY_BOARD=nucleo_g071rb`
- **THEN** the configure pass SHALL NOT issue a git fetch
- **AND** SHALL include the HAL via
  `FetchContent_Declare(alloy SOURCE_DIR
  /path/to/alloy)`

### Requirement: alloy-cli SHALL expose an ``alloy setup`` standalone wizard

The ``alloy setup`` Click command SHALL provide guided interactive
onboarding for fresh contributors.  It SHALL accept:

- ``--board <id>`` — pre-pick a board (skips the picker step).
- ``--family <id>`` — pre-pick a family (validated against
  ``toolchain_registry.known_families()``); mutually exclusive
  with ``--board``.
- ``--auto`` — short-circuit every interactive prompt with the
  default answer (Y on each "install?" prompt).  Useful for
  scripted bootstrap.
- ``--no-tui`` — force the line-based prompt even when STDIN is
  a TTY (for users on terminals where Textual misbehaves).
- ``--project-dir <path>`` — defaults to CWD.

When no project exists at ``--project-dir``, ``setup`` SHALL
embed the ``alloy new`` flow: prompt for a board, scaffold, then
proceed to the install step.  When a project exists, ``setup``
SHALL resolve the family from ``alloy.toml`` (mirroring
``alloy doctor --for``) and skip straight to the install plan.

After every successful run, ``setup`` SHALL print "next steps"
naming the concrete commands to run (``alloy build``,
``alloy flash``, ``alloy ui``).

#### Scenario: setup outside a project scaffolds then installs

- **WHEN** the user runs ``alloy setup --project-dir <empty> --board
  nucleo_g071rb --auto``
- **THEN** the directory SHALL contain a scaffolded project
  (``alloy.toml`` + ``CMakeLists.txt`` + ``src/main.cpp`` + …)
- **AND** ``.alloy/toolchain.lock`` SHALL pin every required
  non-vendor tool from the stm32g0 family
- **AND** the toolchain store under ``ALLOY_TOOLS_ROOT`` SHALL
  contain the matching extractions
- **AND** the command SHALL exit 0 with a "next steps" panel
  naming ``alloy build``

#### Scenario: setup inside a project skips scaffolding and installs

- **WHEN** the user runs ``alloy setup --auto`` inside a project
  whose ``alloy.toml`` resolves to ``stm32g0``
- **THEN** the scaffold step SHALL be skipped (no overwrite of
  existing project files)
- **AND** the install step SHALL run, populating
  ``.alloy/toolchain.lock``
- **AND** the run SHALL succeed even when the lockfile is partial
  (additive update for missing tools only)

#### Scenario: setup with --auto in CI never prompts

- **WHEN** ``alloy setup --auto --project-dir <path>`` is run
  with STDIN closed
- **THEN** no prompt SHALL be issued
- **AND** the run SHALL complete with the default answers

#### Scenario: setup with --no-tui falls back to the line prompt

- **WHEN** the user runs ``alloy setup --no-tui`` in a TTY
- **THEN** the family picker SHALL render as a line-based prompt
  (numbered list + ``> `` input)
- **AND** the install plan SHALL render as a Rich table without
  spawning a Textual app

#### Scenario: setup gracefully exits on Ctrl-C mid-prompt

- **WHEN** the user sends SIGINT during a wizard prompt
- **THEN** ``alloy setup`` SHALL exit with code 130
- **AND** the partial state (if any tools were installed before
  the cancel) SHALL remain in the store
- **AND** the output SHALL surface the partial-progress summary

### Requirement: alloy-cli SHALL expose ``alloy reset`` for non-destructive target reset

The ``alloy reset`` Click command SHALL issue a CPU or hardware
reset of the connected probe target, dispatching through
``core.probe_orchestrator.reset_target``.  Flags:

- ``--soft`` (default) — software reset via the probe's standard
  reset command.
- ``--hard`` — pulses the nRST line if the probe + target support
  it.
- ``--halt-after-reset`` — leaves the core halted after reset so
  the user can attach a debugger.
- ``--probe <vid:pid:serial>`` — explicit probe selector matching
  ``alloy flash --probe`` semantics.
- ``--project-dir <path>`` — defaults to CWD; used to resolve
  ``.alloy/toolchain.lock`` for the probe-rs / openocd binary.

When no probe is attached the command SHALL exit non-zero with
``family-toolchain-probe-not-attached``.  When more than one is
attached and ``--probe`` is not given, the command SHALL exit
non-zero with ``family-toolchain-probe-multiple-attached`` and
the message SHALL list every detected probe.

After a successful reset the command SHALL print a Rich panel
summarising the probe id, reset method, and elapsed milliseconds.

#### Scenario: alloy reset on a single-attached Nucleo

- **WHEN** the user runs ``alloy reset`` with one ST-Link
  attached and ``--soft`` (default)
- **THEN** the orchestrator SHALL dispatch a soft reset via
  the lockfile-pinned probe-rs
- **AND** the command SHALL exit 0
- **AND** the output SHALL name the probe id + method

#### Scenario: alloy reset with no attached probe

- **WHEN** the user runs ``alloy reset`` with no probe attached
- **THEN** the command SHALL exit non-zero
- **AND** the output SHALL surface
  ``family-toolchain-probe-not-attached``
- **AND** the message SHALL link to
  ``ERROR_COOKBOOK.md#family-toolchain-probe-not-attached``

#### Scenario: alloy reset with multiple attached probes

- **WHEN** the user runs ``alloy reset`` with two probes attached
  and no ``--probe`` selector
- **THEN** the command SHALL exit non-zero
- **AND** the output SHALL list every probe (vid:pid:serial)
- **AND** SHALL surface
  ``family-toolchain-probe-multiple-attached``

### Requirement: alloy-cli SHALL expose ``alloy erase`` with two safety gates

The ``alloy erase`` Click command SHALL erase the chip's flash
through ``core.probe_orchestrator.{plan_erase, execute_erase}``.
Flags:

- ``--region <name|range>`` — partial erase.  Names resolve via
  the device IR's flash bank descriptors.  Ranges use
  ``0xBASE-0xEND`` syntax.  May be repeated to erase several
  regions in one run.
- ``--auto`` / ``--yes`` — suppresses the confirmation prompt.
  Required in non-TTY contexts (CI, subprocess piping); the
  command SHALL refuse to proceed in non-TTY without one of them.
- ``--probe <vid:pid:serial>`` — same selector as ``alloy reset``.
- ``--project-dir <path>``.

In a TTY the command SHALL print the plan (regions + total bytes
+ chip id) and prompt:

```
This will erase <total_bytes> on <chip_id>. Continue? [y/N]
```

Default answer N.  Anything other than ``y`` / ``yes`` (case-
insensitive) SHALL surface
``family-toolchain-erase-aborted`` with exit code 1.  ``--auto``
or ``--yes`` SHALL bypass the prompt.

When ``--region <name>`` does not resolve via the device IR the
command SHALL exit non-zero with
``family-toolchain-erase-unsupported-region`` and the message
SHALL list every region the IR knows about.

#### Scenario: alloy erase in a TTY answered Y

- **WHEN** the user runs ``alloy erase`` with one probe attached
  and answers ``y`` at the prompt
- **THEN** the command SHALL execute the chip-wide erase
- **AND** SHALL exit 0
- **AND** the output SHALL summarise total bytes erased + duration

#### Scenario: alloy erase in a TTY answered N

- **WHEN** the user answers ``n`` at the prompt
- **THEN** no erase SHALL run
- **AND** the command SHALL exit non-zero
- **AND** SHALL surface ``family-toolchain-erase-aborted``

#### Scenario: alloy erase --auto in CI

- **WHEN** the user runs ``alloy erase --auto`` with STDIN closed
- **THEN** no prompt SHALL fire
- **AND** the orchestrator SHALL execute the erase
- **AND** the command SHALL exit 0 on success

#### Scenario: alloy erase without --auto in non-TTY

- **WHEN** the user runs ``alloy erase`` with STDIN closed and no
  ``--auto`` / ``--yes``
- **THEN** the command SHALL exit non-zero
- **AND** SHALL surface ``family-toolchain-erase-aborted`` with
  a message naming the missing flag

#### Scenario: alloy erase --region resolves a named alias

- **WHEN** the user runs ``alloy erase --region bootloader
  --auto`` against a chip whose IR declares a ``bootloader``
  flash region
- **THEN** the orchestrator SHALL plan the erase against the
  resolved region only
- **AND** SHALL execute that subset

#### Scenario: alloy erase --region with an unknown alias

- **WHEN** the user runs ``alloy erase --region not-a-region``
- **THEN** the command SHALL exit non-zero
- **AND** SHALL surface
  ``family-toolchain-erase-unsupported-region``
- **AND** the message SHALL list the region names the IR exposes

### Requirement: alloy-cli SHALL expose ``alloy monitor`` for live UART / RTT viewing

The ``alloy monitor`` Click command SHALL stream bytes from the
target's debug UART (or RTT channel) to stdout.  Flags:

- ``--port <path>`` — explicit serial device; overrides
  autodetect.
- ``--baud <N>`` — explicit baud rate; overrides
  ``alloy.toml [uart].debug.baud``.
- ``--mode raw`` (default) | ``--mode rtt``.
- ``--ansi/--no-ansi`` (default ``--no-ansi``) — pass-through ANSI
  escape sequences when set; strip them otherwise.
- ``--probe <vid:pid:serial>`` — only meaningful in ``rtt``
  mode.
- ``--project-dir <path>``.

When neither ``--port`` nor a project ``[uart].debug`` config
resolves the command SHALL exit non-zero with a clear message.

Pressing ``Ctrl+]`` SHALL raise
``ProbeOperationCancelledError`` from the orchestrator; the
command SHALL catch it and print a one-line summary:

```
Closed monitor session.  <bytes> bytes captured over <duration>.
Last line: "<line>"
```

The exit code SHALL be 0 (graceful disconnect is not a failure).

#### Scenario: alloy monitor inside a project with debug UART configured

- **WHEN** the user runs ``alloy monitor`` inside a project whose
  ``alloy.toml`` declares ``[uart].debug.peripheral``
- **THEN** the command SHALL open the resolved serial device at
  the configured baud
- **AND** stream bytes to stdout

#### Scenario: alloy monitor outside a project with explicit overrides

- **WHEN** the user runs ``alloy monitor --port /dev/cu.usb1234
  --baud 115200`` outside a project
- **THEN** the command SHALL open the explicit port at the
  explicit baud

#### Scenario: alloy monitor Ctrl+] graceful close

- **WHEN** the user presses Ctrl+] mid-session
- **THEN** the command SHALL close the session cleanly
- **AND** print the summary line with byte count + duration
- **AND** exit 0

#### Scenario: alloy monitor with no port and no project config

- **WHEN** the user runs ``alloy monitor`` outside a project
  with no ``--port``
- **THEN** the command SHALL exit non-zero with a clear message
  naming ``--port`` and the project's ``[uart].debug`` field

