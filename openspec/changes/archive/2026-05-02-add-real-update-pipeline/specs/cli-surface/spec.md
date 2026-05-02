## ADDED Requirements

### Requirement: alloy update SHALL actually upgrade pip + submodule components

`alloy update` SHALL invoke real upgraders for each pinned
component (`alloy-devices-yml` via git submodule, `alloy-codegen`
/ `alloy` / `alloy-cli` via pip).  Upgraders SHALL run in
dependency order — devices → codegen → alloy → alloy-cli — and
the lockfile SHALL be rewritten only when every step succeeds.
Any non-zero return code SHALL abort the sequence and leave the
lockfile bytes unchanged.

#### Scenario: alloy update upgrades pip packages and rewrites the lockfile

- **WHEN** `alloy.toml` pins `alloy = "0.7.5"` and
  `.alloy/version.lock` records `alloy = "0.7.3"`
- **AND** the user runs `alloy update`
- **THEN** the command SHALL invoke
  `python -m pip install --upgrade alloy==0.7.5` exactly once
- **AND** the lockfile SHALL be rewritten with `alloy = "0.7.5"`
- **AND** the success summary SHALL list the upgraded component
  per row

#### Scenario: a failing upgrader leaves the lockfile untouched

- **WHEN** `alloy update` is running and the alloy-codegen pip
  install exits non-zero
- **THEN** the command SHALL exit non-zero
- **AND** the lockfile bytes on disk SHALL be byte-identical to
  the pre-update state
- **AND** the failure summary SHALL name the failing component
  and surface the captured stderr tail

#### Scenario: upgrading alloy-cli reminds the user to restart the process

- **WHEN** `alloy-cli` itself is among the upgraded components
- **THEN** the upgrade summary SHALL include a reminder to
  re-launch `alloy` so the new version is on PATH
- **AND** the lockfile SHALL still be rewritten before the
  reminder prints
