## ADDED Requirements

### Requirement: alloy-cli SHALL expose an `alloy toolchain` subcommand group with five verbs

The `alloy toolchain` Click group SHALL ship with five subcommands:

- `install [--for <family>] [--shared] [--dry-run] [--project-dir
  <dir>]` — install every required and non-vendor recommended
  tool for the chosen family into the content-addressed store.
  `--shared` writes only the global store (no project-local
  lockfile update); `--dry-run` prints the plan + total estimated
  size and writes nothing.
- `list [--installed/--missing] [--for <family>] [--json]
  [--project-dir <dir>]` — show what is installed (with sizes)
  and what is missing for the project's resolved family or the
  override.
- `use <tool>@<version> [--project-dir <dir>]` — pin a specific
  version in `.alloy/toolchain.lock`.  Errors when the requested
  pin is not in any shipped `data/sources/*.json`.
- `prune [--dry-run]` — delete store entries no project's
  `.alloy/toolchain.lock` references.
- `shell [--for <family>] [--project-dir <dir>]` — spawn the
  user's `$SHELL` (or `cmd.exe` on Windows) with the cached
  binaries' bin directories prepended to `PATH`.  PATH
  augmentation lives only inside the spawned subshell and
  ends when the user `exit`s.

#### Scenario: `alloy toolchain install --dry-run --for esp32` writes nothing

- **WHEN** the user runs
  `alloy toolchain install --dry-run --for esp32`
- **THEN** the command SHALL print every planned tool with
  its URL + sha256 + estimated size
- **AND** the command SHALL print the total estimated size
- **AND** the command SHALL exit 0
- **AND** the toolchain store SHALL contain no new entries
  after the run
- **AND** no project lockfile SHALL be created or modified

#### Scenario: `alloy toolchain list --json` reports installed and missing

- **WHEN** the user runs
  `alloy toolchain list --for stm32g0 --json --project-dir <root>`
- **AND** the store has `arm-none-eabi-gcc 14.2.0` but lacks
  `probe-rs`
- **THEN** the JSON output SHALL include
  `arm-none-eabi-gcc` with `installed=true`,
  `version="14.2.0"`, and a non-zero `size_bytes`
- **AND** the JSON output SHALL include `probe-rs` with
  `installed=false`

#### Scenario: `alloy toolchain use <tool>@<version>` updates the lockfile

- **WHEN** the user runs `alloy toolchain use
  arm-none-eabi-gcc@14.2.0` in a project root
- **THEN** `.alloy/toolchain.lock` SHALL contain the
  `[tools]."arm-none-eabi-gcc"` entry with
  `version = "14.2.0"` and the matching pinned `sha256`
- **AND** the file SHALL parse via
  `lockfile_toolchain.read(path)` without diagnostics

#### Scenario: `alloy toolchain prune --dry-run` lists candidates without deleting

- **WHEN** the user runs `alloy toolchain prune --dry-run`
- **AND** the store has versions no project's lockfile pins
- **THEN** the output SHALL list every prunable
  `<sha>/<tool>@<version>` triple with its size
- **AND** the store SHALL retain every listed version

#### Scenario: `alloy toolchain shell` augments PATH for the spawned subshell

- **WHEN** the user runs `alloy toolchain shell --for stm32g0`
- **AND** at least one tool is installed in the store
- **THEN** the spawned subshell's `PATH` SHALL include the
  store's `bin` directories before the user's existing PATH
- **AND** running `which arm-none-eabi-gcc` inside the
  subshell SHALL print a path under
  `~/.local/share/alloy/tools/by-name/`
- **AND** exiting the subshell SHALL leave the parent
  shell's PATH unmodified

## MODIFIED Requirements

### Requirement: alloy-cli SHALL build, flash, and debug projects with one command each

`alloy build`, `alloy flash`, and `alloy debug` SHALL be the
single user-facing verbs for those operations.  Each SHALL detect
required toolchains and probes automatically; SHALL surface an
actionable install hint when a dependency is missing; SHALL stream
live progress; and SHALL never require the user to invoke `cmake`,
`probe-rs`, or `gdb` directly.

When the project carries `.alloy/toolchain.lock`, the three verbs
SHALL prefer the cached binary path resolved by
`toolchain_manager.resolve(...)` over the system PATH.
`alloy build` SHALL pass `-DCMAKE_TOOLCHAIN_FILE=` pointing at
the generated `.alloy/cache/toolchain.cmake` whenever the
lockfile exists.  `alloy flash` and `alloy debug` SHALL invoke
`probe-rs` / `arm-none-eabi-gdb` from the store first, falling
back to `shutil.which` only when the lockfile is missing or the
store entry has been removed.

When the lockfile pins a `(tool, version, sha256)` triple that
does not match the store, the affected verb SHALL exit non-zero
with `family-toolchain-installer-version-mismatch` and SHALL
suggest `alloy toolchain install`.

#### Scenario: `alloy build` uses the cached compiler when locked

- **WHEN** the project has
  `.alloy/toolchain.lock` pinning `arm-none-eabi-gcc 14.2.0`
- **AND** the store has the matching extraction
- **AND** the user runs `alloy build`
- **THEN** the cmake invocation SHALL pass
  `-DCMAKE_TOOLCHAIN_FILE=<path>/.alloy/cache/toolchain.cmake`
- **AND** the toolchain file SHALL set `CMAKE_C_COMPILER`
  to an absolute path under the toolchain store
- **AND** PATH augmentation SHALL NOT be performed

#### Scenario: `alloy flash` prefers the cached probe-rs

- **WHEN** the lockfile pins `probe-rs 0.27.0`
- **AND** the store has the matching extraction
- **AND** the user runs `alloy flash`
- **THEN** the spawned subprocess argv SHALL begin with the
  absolute path under
  `~/.local/share/alloy/tools/by-name/probe-rs/0.27.0/...`
- **AND** SHALL NOT begin with a bare `probe-rs`

#### Scenario: missing tool from lockfile errors loudly

- **WHEN** the lockfile pins `probe-rs 0.27.0` but the
  store has only `probe-rs 0.26.0`
- **AND** the user runs `alloy flash`
- **THEN** the command SHALL exit non-zero with
  `family-toolchain-installer-version-mismatch`
- **AND** the message SHALL suggest `alloy toolchain install`

#### Scenario: legacy projects without lockfile keep building

- **WHEN** the project has no `.alloy/toolchain.lock`
- **AND** the user runs `alloy build`
- **THEN** the cmake invocation SHALL NOT carry
  `-DCMAKE_TOOLCHAIN_FILE`
- **AND** behaviour SHALL match the pre-Wave-2 baseline
