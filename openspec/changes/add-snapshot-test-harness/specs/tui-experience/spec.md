## ADDED Requirements

### Requirement: TUI screens SHALL be pinned with SVG snapshot tests

Every Textual screen shipped by alloy-cli SHALL have a
corresponding SVG golden under `tests/snapshots/` that
`pytest-textual-snapshot` compares against on every run.  The
golden SHALL be regenerated via `pytest --snapshot-update` and
SHALL match byte-for-byte the SVG that the same render path
produces in `docs/images/`.  CI SHALL fail when any pinned
screen drifts; the failure SHALL print the regenerated SVG path
so reviewers can audit the diff in the PR.

#### Scenario: a screen layout regression fails CI

- **WHEN** a contributor changes `DashboardScreen.compose` so
  that the toolchain row drops a pill
- **AND** the snapshot test runs without `--snapshot-update`
- **THEN** the test SHALL fail with a non-zero exit code
- **AND** the failure message SHALL name the affected SVG and
  the command to refresh it
- **AND** the contributor SHALL be able to inspect the diff via
  `git diff tests/snapshots/02-dashboard.svg`

#### Scenario: docs/images stays in sync with the snapshot goldens

- **WHEN** the snapshot tests pass for every pinned screen
- **AND** `python scripts/generate_docs_images.py` is rerun
- **THEN** the SVGs under `docs/images/` SHALL match their
  counterparts in `tests/snapshots/` byte-for-byte
