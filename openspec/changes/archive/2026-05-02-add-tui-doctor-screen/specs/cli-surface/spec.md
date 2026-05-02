## ADDED Requirements

### Requirement: alloy doctor SHALL support a non-interactive `--fix` mode

`alloy doctor --fix` SHALL iterate over every check whose
`CheckResult.auto_fix` is non-None and run the registered fixer
through `core.process.runner`.  The command SHALL exit 0 iff
every error-severity row passes after the fixers run; otherwise
SHALL exit 1 with a per-check status summary.

#### Scenario: --fix initialises the alloy-devices-yml submodule

- **WHEN** the alloy-devices-yml submodule is uninitialised
- **AND** the user runs `alloy doctor --fix`
- **THEN** the command SHALL invoke
  `git submodule update --init` exactly once
- **AND** the command SHALL exit 0 if the post-fix re-run shows
  every check passing

#### Scenario: --fix surfaces a failing fixer with non-zero exit

- **WHEN** an auto-fix returns `ok=False`
- **AND** the underlying check is error-severity
- **THEN** the command SHALL exit 1
- **AND** the summary SHALL include the captured stderr tail and
  the unchanged install hint
