# developer-experience Specification

## Purpose
TBD - created by archiving change add-quickstart-and-cookbook. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL ship a five-minute quickstart, progressive examples, and a typed error cookbook

The repo SHALL include a `docs/QUICKSTART.md` walkthrough that
takes a new user from `pip install` to a flashed Nucleo-G071RB
without leaving the page.  `docs/EXAMPLES/` SHALL hold at least
four progressive examples (`01-blinky`, `02-uart-echo`,
`03-spi-flash`, `04-dma-double-buffer`), each with a
`README.md`, a parseable `alloy.toml`, and the generated
`peripherals.cpp` for reviewers to diff.  `docs/ERROR_COOKBOOK.md`
SHALL document every `error_type` emitted by
`AlloyCliError`; CI SHALL block merges when an `error_type`
declared in code lacks a matching cookbook anchor.

#### Scenario: a new user blinks an LED in five minutes

- **WHEN** the user follows `docs/QUICKSTART.md` end-to-end on
  a fresh machine with a Nucleo-G071RB attached
- **THEN** `alloy build` SHALL succeed
- **AND** `alloy flash` SHALL leave the user with a blinking
  on-board LED
- **AND** every command block in QUICKSTART SHALL match the
  shipped CLI (verified by a smoke test)

#### Scenario: every error_type has cookbook coverage

- **WHEN** CI runs `scripts/check_error_cookbook.py`
- **THEN** the script SHALL discover every `error_type`
  string declared in `alloy_cli.core.errors`
- **AND** SHALL fail when any `error_type` lacks a matching
  `## error-type-string` anchor in
  `docs/ERROR_COOKBOOK.md`

### Requirement: alloy new --from-example SHALL scaffold from the docs example tree

`alloy new --from-example <name>` SHALL accept any
sub-directory of `docs/EXAMPLES/` and SHALL copy the
`alloy.toml` (re-parented to the user's project name) plus the
example's `peripherals.cpp` skeleton into the target directory.
Unknown example names SHALL exit non-zero with the available
choices in the message.

#### Scenario: --from-example 01-blinky scaffolds a working project

- **WHEN** the user runs `alloy new myblinky --from-example
  01-blinky`
- **THEN** the new project's `alloy.toml` SHALL parse via
  `core.project.read` without diagnostics
- **AND** SHALL declare the same `[board]` and the same
  `[[peripherals]]` array as the example fixture
- **AND** `alloy build --profile debug` SHALL succeed without
  further user edits

### Requirement: Generated cheatsheet stays in sync with the Click tree

`docs/CHEATSHEET.md` SHALL be produced by
`scripts/generate_cheatsheet.py`, which walks the Click command
tree and renders a single-page reference of every subcommand +
its primary flags.  CI SHALL run the script in `--check` mode
on every PR and SHALL fail when the file would drift.

#### Scenario: adding a new CLI subcommand triggers a cheatsheet update

- **WHEN** a contributor lands a new `alloy.<cmd>` entry point
  without re-running the generator
- **THEN** CI SHALL fail the cheatsheet check
- **AND** the failure message SHALL print the diff between
  expected and actual content

