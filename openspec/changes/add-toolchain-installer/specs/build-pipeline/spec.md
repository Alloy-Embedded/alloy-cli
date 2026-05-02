## ADDED Requirements

### Requirement: alloy-cli SHALL stamp the CMake toolchain file alongside the codegen stamp

`core.build.run` SHALL extend its stamp pipeline so the cmake
configure step is rerun when EITHER the codegen stamp invalidates
OR the lockfile / toolchain-file stamp invalidates.

The toolchain stamp SHALL be persisted under
`.alloy/cache/toolchain.cmake.stamp` carrying:

- `lockfile_sha`: SHA-256 of `.alloy/toolchain.lock` text (or the
  literal `none` when no lockfile exists).
- `alloy_cli_version`: the running alloy-cli SemVer.

Cmake configure SHALL skip regeneration of
`.alloy/cache/toolchain.cmake` when the stamp matches the
expected value; otherwise the file SHALL be rewritten and the
stamp updated atomically (mirrors the codegen stamp pattern).

#### Scenario: rebuild on unchanged lockfile reuses the toolchain file

- **WHEN** `core.build.run` is invoked twice on a project with
  a stable `.alloy/toolchain.lock`
- **THEN** the second invocation SHALL NOT rewrite
  `.alloy/cache/toolchain.cmake`
- **AND** the toolchain stamp file's modification timestamp
  SHALL NOT change between invocations

#### Scenario: lockfile edit invalidates the toolchain file

- **WHEN** the user edits `.alloy/toolchain.lock` (e.g. via
  `alloy toolchain use`)
- **AND** the user runs `alloy build`
- **THEN** `.alloy/cache/toolchain.cmake` SHALL be rewritten
- **AND** its banner SHALL include the new lockfile sha

#### Scenario: alloy-cli upgrade invalidates the toolchain file

- **WHEN** alloy-cli's pinned version changes between two
  builds without the lockfile changing
- **THEN** the next `alloy build` SHALL rewrite
  `.alloy/cache/toolchain.cmake`
- **AND** the toolchain stamp's `alloy_cli_version` SHALL
  match the new value
