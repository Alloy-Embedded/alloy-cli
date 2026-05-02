## ADDED Requirements

### Requirement: alloy-cli SHALL ship a per-source pinned URL+SHA manifest schema

The repo SHALL include a JSON Schema (Draft 2020-12) at
`schema/source_manifest_v1.json` that validates every per-source-kind
pin file under `data/sources/`.  The schema SHALL require:

- A top-level `schema_version` matching `^1\.[0-9]+\.[0-9]+$`.
- A top-level `source` field declaring the source kind
  (`xpack`, `github`, `probe-rs`, `espressif`).
- A top-level `tools` array of pin entries; each pin SHALL declare:
  - `tool` (string, kebab-case).
  - `version` (string, exact SemVer — pins are version-exact).
  - `hosts` (object keyed on `<os>-<arch>` strings; each value
    declares `url`, `sha256`, `archive_kind`
    (`tar.xz`/`tar.gz`/`zip`/`bin`), `extract_to_subdir`,
    `binaries[]` listing the relative paths inside the extraction).
- `additionalProperties: false` at every object level.

Vendor-source tools SHALL NOT appear in any `data/sources/*.json`
file; their distribution is EULA-gated and Wave 1's renderer owns
them.

#### Scenario: every shipped pin file validates

- **WHEN** the test suite loads
  `schema/source_manifest_v1.json`
- **AND** validates every JSON under `data/sources/`
- **THEN** every pin file SHALL pass validation
- **AND** mutating any required field SHALL surface a
  `jsonschema.ValidationError` flagged in CI

#### Scenario: pin entries cover at least the five canonical hosts

- **WHEN** the test suite walks every shipped pin
- **THEN** each entry SHALL declare `hosts` for at least
  `linux-x86_64`, `linux-arm64`, `macos-x86_64`,
  `macos-arm64`, `windows-x86_64`
- **OR** SHALL document an `unsupported_hosts` field listing
  the host triples that are intentionally unavailable

### Requirement: `core.tool_sources` SHALL adapt every non-vendor source kind to a uniform Source protocol

The `alloy_cli.core.tool_sources` module SHALL expose a
`Source` Protocol with a single method
`resolve(tool: ToolRequirement, host: HostTriple) -> SourceArtifact`.
The module SHALL ship four concrete implementations:

- `XpackAdapter` — reads `data/sources/xpack.json`.
- `GithubAdapter` — reads `data/sources/github.json`; matches the
  `github:<owner>/<repo>` pattern in `tool.source`.
- `ProbeRsAdapter` — reads `data/sources/probe-rs.json`.
- `EspressifAdapter` — reads `data/sources/espressif.json`.

The module SHALL expose a dispatcher
`adapter_for(source: str) -> Source` that returns the matching
adapter for a `ToolRequirement.source` string and raises
`FamilyToolchainInstallerError(error_type=
"family-toolchain-installer-unsupported-host")` for
`source = "vendor"` (callers MUST short-circuit vendor tools).

Adapters SHALL be pure: construction MUST NOT touch the network,
the filesystem outside `data/sources/`, or any environment
variable.

#### Scenario: dispatcher resolves every shipped source string

- **WHEN** the test suite calls `adapter_for(s)` for every
  source string declared in any shipped family manifest
  (`xpack`, `github:<owner>/<repo>`, `probe-rs-installer`,
  `espressif`)
- **THEN** the call SHALL return a `Source`-conforming object
- **AND** SHALL never raise

#### Scenario: vendor source raises, never returns an adapter

- **WHEN** `adapter_for("vendor")` is called
- **THEN** the call SHALL raise
  `FamilyToolchainInstallerError`
- **AND** the message SHALL state vendor tools install manually

#### Scenario: missing host triple raises a typed error

- **WHEN** an adapter resolves a pin whose `hosts` map has
  no entry for the active host triple
- **THEN** the call SHALL raise
  `family-toolchain-installer-unsupported-host`
- **AND** the message SHALL include the actual host triple

### Requirement: `core.toolchain_manager` SHALL provide an atomic, idempotent, content-addressed install pipeline

The `alloy_cli.core.toolchain_manager` module SHALL expose:

- `install(tool: ToolRequirement, *, force: bool = False,
  downloader: Downloader | None = None) -> InstallOutcome`
- `resolve(tool_name: str, *, version: str | None = None) ->
  Path | None`
- `list_installed() -> list[InstalledTool]`
- `prune(*, projects: Sequence[Path], dry_run: bool = False) ->
  PruneReport`
- `verify(tool_name: str) -> bool`

The store SHALL live at
`platformdirs.user_data_dir("alloy")/tools/` with the layout
described in `design.md` D2.  Concurrent installs from different
processes SHALL be serialised via an advisory file lock
(`fcntl.flock` on POSIX, `msvcrt.locking` on Windows).
Re-running install on an already-promoted artefact SHALL be a
no-op (`InstallOutcome.skipped is True`).

#### Scenario: install verifies SHA256 before extraction

- **WHEN** the downloader returns bytes whose SHA256 does
  not match the pin
- **AND** install is invoked
- **THEN** install SHALL raise
  `family-toolchain-installer-checksum`
- **AND** SHALL leave `store/<sha>/` empty
- **AND** SHALL clean up `store/.tmp/<sha>.partial`

#### Scenario: install promotes via os.rename only after extraction completes

- **WHEN** install extracts an artefact successfully
- **THEN** the final move SHALL be a single
  `os.rename(.tmp/<sha>, store/<sha>)`
- **AND** SHALL update `manifest.json` under the same flock

#### Scenario: re-install is a no-op

- **WHEN** install is invoked twice on the same
  `(tool, version)` pin
- **AND** the first call promoted the artefact
- **THEN** the second call SHALL return
  `InstallOutcome(skipped=True)`
- **AND** SHALL NOT touch the network

#### Scenario: concurrent installs serialise via flock

- **WHEN** two `install` calls happen in parallel from
  separate processes
- **AND** the first process holds the flock
- **THEN** the second SHALL raise
  `family-toolchain-installer-locked`
- **AND** the user SHALL be told to retry once the first
  process completes

#### Scenario: store corruption surfaces typed

- **WHEN** `resolve(tool_name)` is called for a tool whose
  `manifest.json` entry exists but whose `store/<sha>/`
  directory does not
- **THEN** the call SHALL return `None`
- **AND** subsequent build / flash / debug invocations SHALL
  raise `family-toolchain-installer-store-corrupt`
- **AND** the message SHALL suggest
  `alloy toolchain install --force`

### Requirement: `.alloy/toolchain.lock` SHALL be the project's exact-pin source of truth

`alloy_cli.core.lockfile_toolchain` SHALL expose
`read(path)` / `write(path, lock)` / `diff(before, after)` /
`add(lock, tool, version, sha256)` / `remove(lock, tool)`.
The on-disk format SHALL be deterministic TOML (sorted keys)
matching:

```toml
schema_version = "1.0.0"
[tools]
"arm-none-eabi-gcc" = { version = "14.2.0", sha256 = "abc..." }
"probe-rs"          = { version = "0.27.0", sha256 = "def..." }
```

The lockfile SHALL be parsed via stdlib `tomllib`; emission SHALL
go through a single `dumps()` function so two callers never
produce divergent text.  An invalid lockfile SHALL raise
`ProjectConfigError` (a Wave 1 error type) rather than a generic
exception.

#### Scenario: lockfile round-trips through dumps

- **WHEN** a lockfile is read, written, and read again
- **THEN** the second-pass parse SHALL equal the first
- **AND** the on-disk byte sequence SHALL be byte-identical

#### Scenario: tool addition preserves alphabetical key order

- **WHEN** `add(lock, "tio", "2.7.0", "...")` is called
  on a lock that already pins `"arm-none-eabi-gcc"` and
  `"cmake"`
- **THEN** the resulting lockfile SHALL emit keys in
  alphabetical order
- **AND** the `[tools]` section SHALL contain three entries

### Requirement: Linux probe support SHALL emit udev rules without invoking sudo

The toolchain manager SHALL emit Linux udev rules without ever
invoking `sudo` itself.  When `install` runs a tool whose family
manifest declares `udev_required: true` on Linux, the manager
SHALL:

- Write the rules content (carried in the source pin) to
  `<base>/alloy/udev/<tool>.rules`.
- Print a one-line `sudo cp <path> /etc/udev/rules.d/ &&
  sudo udevadm control --reload-rules` instruction to the
  caller's `on_line` callback.
- Never invoke `sudo` itself.

On macOS and Windows, `udev_required` is silently ignored.

#### Scenario: probe-rs install emits udev rules on Linux

- **WHEN** install completes successfully on Linux for
  probe-rs
- **THEN** `<base>/alloy/udev/probe-rs.rules` SHALL exist
  and SHALL be readable
- **AND** the emitted instruction SHALL include the
  `sudo udevadm control --reload-rules` step
- **AND** the manager SHALL NOT call `subprocess.run` with
  any argument starting with `sudo`

### Requirement: `FamilyToolchainInstallerError` SHALL extend the AlloyCliError hierarchy with seven typed sub-classes

`alloy_cli.core.errors` SHALL export:

- `FamilyToolchainInstallerError` (base, `error_type =
  "family-toolchain-installer-error"`).
- `FamilyToolchainInstallerChecksumError`
  (`family-toolchain-installer-checksum`).
- `FamilyToolchainInstallerDownloadError`
  (`family-toolchain-installer-download`).
- `FamilyToolchainInstallerExtractError`
  (`family-toolchain-installer-extract`).
- `FamilyToolchainInstallerStoreCorruptError`
  (`family-toolchain-installer-store-corrupt`).
- `FamilyToolchainInstallerVersionMismatchError`
  (`family-toolchain-installer-version-mismatch`).
- `FamilyToolchainInstallerUnsupportedHostError`
  (`family-toolchain-installer-unsupported-host`).
- `FamilyToolchainInstallerLockedError`
  (`family-toolchain-installer-locked`).

Every new `error_type` string SHALL be unique across the entire
`AlloyCliError` hierarchy and SHALL appear with a matching
anchor in `docs/ERROR_COOKBOOK.md`.

#### Scenario: every new error type has a cookbook anchor

- **WHEN** CI runs `scripts/check_error_cookbook.py`
- **THEN** the script SHALL discover every new
  `family-toolchain-installer-*` error type
- **AND** SHALL fail when any error type lacks a matching
  `## family-toolchain-installer-...` anchor in
  `docs/ERROR_COOKBOOK.md`

#### Scenario: error_type strings are unique across the hierarchy

- **WHEN** the test suite walks every concrete subclass of
  `AlloyCliError`
- **THEN** the set of `error_type` strings SHALL contain no
  duplicates

### Requirement: `core.build.run` SHALL generate a CMake toolchain file when `.alloy/toolchain.lock` exists

`core.build.run` SHALL generate `.alloy/cache/toolchain.cmake`
that sets `CMAKE_C_COMPILER`, `CMAKE_CXX_COMPILER`, and
`CMAKE_ASM_COMPILER` to absolute paths inside the toolchain
store whenever the project carries `.alloy/toolchain.lock`.  Generation SHALL be stamp-keyed on
`sha256(lockfile_text + alloy_cli_version)`; a fresh build
on an unchanged lockfile SHALL skip regeneration.  CMake
SHALL be invoked with
`-DCMAKE_TOOLCHAIN_FILE=.alloy/cache/toolchain.cmake`.

When no `.alloy/toolchain.lock` exists, the build SHALL
fall back to today's behaviour (cmake resolves compilers
via PATH).

#### Scenario: lockfile presence triggers toolchain file generation

- **WHEN** `core.build.run` is invoked on a project with a
  fresh `.alloy/toolchain.lock` pinning
  `arm-none-eabi-gcc 14.2.0`
- **THEN** `.alloy/cache/toolchain.cmake` SHALL exist after
  the run
- **AND** SHALL contain a `set(CMAKE_C_COMPILER "<absolute
  path inside the store>")` line
- **AND** the cmake configure invocation SHALL pass
  `-DCMAKE_TOOLCHAIN_FILE=` pointing at that file

#### Scenario: missing tool raises typed version-mismatch

- **WHEN** the lockfile pins `probe-rs 0.27.0` but the
  store only has `probe-rs 0.26.0`
- **AND** `core.build.run` is invoked
- **THEN** the run SHALL raise
  `family-toolchain-installer-version-mismatch`
- **AND** the message SHALL include the pinned and
  installed versions
- **AND** SHALL suggest `alloy toolchain install`

#### Scenario: legacy projects keep building unchanged

- **WHEN** `core.build.run` is invoked on a project with no
  `.alloy/toolchain.lock`
- **THEN** the run SHALL NOT generate a toolchain file
- **AND** the cmake invocation SHALL NOT carry
  `-DCMAKE_TOOLCHAIN_FILE`
- **AND** the build behaviour SHALL match today's

### Requirement: `alloy toolchain install` SHALL skip vendor tools with an explicit notice

`alloy toolchain install` SHALL skip every `source: vendor`
entry with an explicit "skipped (vendor — install manually)"
log line and SHALL never contact a vendor download endpoint.
The manager SHALL iterate `family.required + family.recommended`
and dispatch every entry whose `source != "vendor"` to its
source adapter.
Vendor entries SHALL be skipped with a single explicit log line:

```
✗ <tool> skipped (vendor — install manually: <install_doc URL>)
```

The exit code SHALL be 0 even when only vendor tools were
"skipped" — vendor absence is informational, never an error
(mirrors Wave 1's diagnostic severity).

#### Scenario: stm32g0 install does NOT download STM32CubeProgrammer

- **WHEN** the user runs `alloy toolchain install --for stm32g0`
- **THEN** the install SHALL complete without contacting
  `st.com`
- **AND** the output SHALL contain
  `STM32CubeProgrammer skipped (vendor`
- **AND** the per-OS install_docs URL SHALL appear on the
  same line
- **AND** the exit code SHALL be 0
