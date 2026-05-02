## ADDED Requirements

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
