## Why

Wave 1 (`add-toolchain-registry`, archived once merged) gave alloy-cli
a per-MCU-family toolchain *map*: `alloy doctor --for stm32g0` lists the
right tools, and `alloy.list_family_toolchain` exposes the same data to
LLM agents.  But every "missing tool" row still tells the user
"Wave-2 will install via xpack."  Today, they have to copy-paste shell
commands and manage PATH conflicts themselves.

This proposal makes the installer real.  alloy-cli will download,
verify-by-SHA256, extract, and self-host every non-vendor tool a
project's family declares — without ever touching the user's PATH.
Build / flash / debug invocations resolve absolute paths to the cached
binaries via a generated CMake toolchain file and direct `subprocess`
arguments.  Vendor (EULA-gated) tools — STM32CubeProgrammer, nrfjprog,
J-Link, Atmel Studio — STAY detect+link only; the installer must
never auto-install them.

Wave 2 unlocks two later waves.  Wave 3 (`add-onboarding-wizard`) wires
this into `alloy new` post-scaffold prompts and the TUI Onboarding
screen.  Wave 4 (`add-recovery-tools`) layers `alloy reset / erase /
monitor` over the same content-addressed store.

## What Changes

- New JSON Schema `schema/source_manifest_v1.json` (Draft 2020-12)
  validating every source-pin file under `data/sources/`.  Each pin
  declares `tool`, `version`, per-host (os + arch) `url` + `sha256`
  + `archive_kind` + `extract_to_subdir` + `binaries[]`.
- New data tree `data/sources/` with one JSON per source kind:
  - `xpack.json` — arm-none-eabi-gcc, cmake, ninja, riscv-none-elf-gcc,
    openocd.
  - `github.json` — picotool, esptool, dfu-util, tio.
  - `probe-rs.json` — probe-rs releases (CMSIS-DAP / J-Link / ST-Link).
  - `espressif.json` — xtensa-esp-elf-gcc, riscv32-esp-elf-gcc.
- New core module `alloy_cli.core.tool_sources` exposing typed adapters
  (`XpackAdapter`, `GithubAdapter`, `ProbeRsAdapter`, `EspressifAdapter`)
  behind a `Source` protocol.  Adapters are pure: they read only from
  the pinned JSON files + the host triple.  Construction never touches
  the network.  `data/sources/*.json` is the ONLY trust boundary.
- New core module `alloy_cli.core.toolchain_manager` owning the
  content-addressed store at `platformdirs.user_data_dir("alloy")/tools/`.
  Atomic install with SHA256 verification and `os.rename`-based
  promotion; advisory file lock for concurrent installs; idempotent
  re-runs.
- New project-local lockfile `.alloy/toolchain.lock` (TOML) pinning
  exact `(version, sha256)` per tool consumed by the project.
  Separate from the existing `version.lock` (alloy-cli /
  alloy-codegen / alloy-devices-yml).
- New `alloy toolchain` Click subcommand group with five verbs:
  `install`, `list`, `use`, `prune`, `shell`.  None of them write to
  the user's shell config — `alloy toolchain shell` spawns a sub-
  shell with PATH augmented for the lifetime of that subshell only.
- `core.build.run` writes `.alloy/cache/toolchain.cmake` whenever the
  lockfile changes (stamp-keyed on lockfile sha + alloy-cli version).
  CMake is invoked with `-DCMAKE_TOOLCHAIN_FILE=…/toolchain.cmake`
  setting `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` /
  `CMAKE_ASM_COMPILER` to absolute paths in the store.  When no
  lockfile exists, the build falls back to today's behaviour
  (PATH-resolved compilers) so existing projects keep building.
- `core.flash.run` and `core.debug.build_invocation` resolve `probe-rs`
  / `arm-none-eabi-gdb` via `toolchain_manager.resolve(...)` first,
  falling back to `shutil.which` so existing user setups keep working.
- New typed errors under `FamilyToolchainInstallerError`:
  `family-toolchain-installer-checksum`,
  `family-toolchain-installer-download`,
  `family-toolchain-installer-extract`,
  `family-toolchain-installer-store-corrupt`,
  `family-toolchain-installer-version-mismatch`,
  `family-toolchain-installer-unsupported-host`,
  `family-toolchain-installer-locked`.
- Linux udev handling: when a `udev_required: true` tool installs,
  alloy-cli writes `<user_data>/alloy/udev/<tool>.rules` and emits a
  one-line `sudo cp … && sudo udevadm control --reload-rules`
  instruction.  Sudo is *never* run silently.
- New MCP read-only tools:
  - `alloy.toolchain_status(family_id?)` — Wave 1's
    `list_family_toolchain` enriched with per-tool installed /
    missing / version-mismatch state from the store.
  - `alloy.toolchain_install_plan(family_id)` — returns the planned
    download set (URL + sha256 + size) without performing any I/O.
- New documentation: `docs/TOOLCHAIN_INSTALLER.md` covers the source
  adapter contract and the workflow for refreshing the pinned
  URL+SHA tables.  `scripts/refresh_source_pins.py` updates
  `data/sources/*.json` from upstream release feeds (run by hand or
  on a CI cadence; output is a PR for human review, never pushed
  automatically).

## Capabilities

### New Capabilities

- `toolchain-installer`: source-adapter contract, content-addressed
  store layout, project-local lockfile, the `alloy toolchain`
  command group, the CMake toolchain file generation pipeline, and
  the typed `FamilyToolchainInstallerError` hierarchy.

### Modified Capabilities

- `cli-surface`: the new `alloy toolchain` subcommand group is
  added; `alloy build` / `alloy flash` / `alloy debug` gain
  toolchain-store awareness (preferring the cached binary path
  before falling back to PATH).
- `build-pipeline`: the cmake configure step gains the
  `CMAKE_TOOLCHAIN_FILE` argument when a project lockfile exists;
  the codegen + cmake stamps mention the toolchain file in their
  invalidation key.
- `mcp-surface`: two new read-only tools (`toolchain_status`,
  `toolchain_install_plan`) join the existing read-only set.

## Impact

- **New code**: `src/alloy_cli/core/tool_sources.py`,
  `src/alloy_cli/core/toolchain_manager.py`,
  `src/alloy_cli/core/lockfile_toolchain.py` (read/write/diff for
  `.alloy/toolchain.lock`), `src/alloy_cli/commands/toolchain.py`
  (Click group), `src/alloy_cli/data/sources/*.json`,
  `schema/source_manifest_v1.json`,
  `scripts/refresh_source_pins.py`,
  `docs/TOOLCHAIN_INSTALLER.md`.
- **Modified code**: `src/alloy_cli/core/errors.py` (new error
  hierarchy), `src/alloy_cli/core/build.py` (toolchain file
  generation + path resolution), `src/alloy_cli/core/flash.py`
  (resolve probe-rs via store), `src/alloy_cli/core/debug.py`
  (resolve gdb via store), `src/alloy_cli/main.py` (register the
  `toolchain` group), `src/alloy_cli/mcp/tools.py` (add the two
  read-only tools), `pyproject.toml` (ship the new schema +
  source pins as wheel data), `docs/CHEATSHEET.md` (regenerated),
  `docs/ERROR_COOKBOOK.md` (anchors for the seven new error types).
- **Dependencies**: no new runtime dependencies.  Downloads use
  stdlib `urllib.request`; extraction uses stdlib `tarfile` /
  `zipfile`.  `platformdirs` is already pinned.  The opt-in
  `scripts/refresh_source_pins.py` may use `urllib.request` for
  GitHub / xpack release-feed scraping.
- **Backward compatibility**: fully additive at the user surface.
  Projects with no `.alloy/toolchain.lock` continue to build via
  PATH-resolved compilers with no behavioural change.  The
  existing `core.diagnose` family-aware checks shipped in Wave 1
  do not change shape — only the install hint copy moves from
  "Wave-2 will install via xpack" to "run `alloy toolchain
  install`".
- **Trust boundary**: every URL alloy-cli fetches at runtime
  comes from `data/sources/*.json` (committed to the repository).
  The runtime never resolves a URL from a user-controlled
  argument; it never follows redirects to a domain not encoded
  in the pinned manifest; it never performs DNS or HTTP without a
  matching SHA256.  Adversarial supply-chain mitigations live in
  `design.md`.
- **Out of scope (Waves 3-4)**: `alloy new` post-scaffold install
  prompt; TUI Onboarding screen integration; `alloy doctor --fix`
  invoking the installer; `alloy reset / erase / monitor`;
  EULA-gated guided detection beyond the link rendering Wave 1
  already provides.
