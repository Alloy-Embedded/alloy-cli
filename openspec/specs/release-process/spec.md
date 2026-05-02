# release-process Specification

## Purpose
TBD - created by archiving change harden-release-and-injection. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL ship a documented release process gated by hardware-in-the-loop CI

The repo SHALL include `docs/RELEASING.md` describing the steps
to cut a release (tag, `gh release create`, PyPI trusted
publishing, post-release version bump, CHANGELOG update).
`.github/workflows/release.yml` SHALL run a pre-publish smoke
step that installs the freshly-built wheel and runs `alloy
--version`.  A `.github/workflows/hil.yml` workflow SHALL run a
scaffold + build pipeline against at least one board on a
self-hosted runner; a failure SHALL block the release.

#### Scenario: release workflow refuses to publish when the smoke step fails

- **WHEN** a maintainer pushes a `v*` tag
- **AND** `pip install dist/*.whl && alloy --version` exits
  non-zero in the workflow
- **THEN** the release job SHALL fail
- **AND** the PyPI publish step SHALL NOT execute

#### Scenario: HIL workflow blocks a regression that breaks the scaffold

- **WHEN** a PR lands a change that breaks
  `alloy new firmware --board nucleo_g071rb`
- **AND** the HIL workflow runs against the resulting tree on
  the self-hosted runner
- **THEN** the workflow SHALL fail with a non-zero return code
- **AND** the failing log SHALL surface the cmake / ninja
  output for diagnosis

