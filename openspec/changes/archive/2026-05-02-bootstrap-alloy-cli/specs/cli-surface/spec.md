## ADDED Requirements

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
