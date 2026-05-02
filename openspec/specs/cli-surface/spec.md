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

