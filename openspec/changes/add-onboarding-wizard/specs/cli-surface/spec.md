## ADDED Requirements

### Requirement: alloy-cli SHALL expose an ``alloy setup`` standalone wizard

The ``alloy setup`` Click command SHALL provide guided interactive
onboarding for fresh contributors.  It SHALL accept:

- ``--board <id>`` — pre-pick a board (skips the picker step).
- ``--family <id>`` — pre-pick a family (validated against
  ``toolchain_registry.known_families()``); mutually exclusive
  with ``--board``.
- ``--auto`` — short-circuit every interactive prompt with the
  default answer (Y on each "install?" prompt).  Useful for
  scripted bootstrap.
- ``--no-tui`` — force the line-based prompt even when STDIN is
  a TTY (for users on terminals where Textual misbehaves).
- ``--project-dir <path>`` — defaults to CWD.

When no project exists at ``--project-dir``, ``setup`` SHALL
embed the ``alloy new`` flow: prompt for a board, scaffold, then
proceed to the install step.  When a project exists, ``setup``
SHALL resolve the family from ``alloy.toml`` (mirroring
``alloy doctor --for``) and skip straight to the install plan.

After every successful run, ``setup`` SHALL print "next steps"
naming the concrete commands to run (``alloy build``,
``alloy flash``, ``alloy ui``).

#### Scenario: setup outside a project scaffolds then installs

- **WHEN** the user runs ``alloy setup --project-dir <empty> --board
  nucleo_g071rb --auto``
- **THEN** the directory SHALL contain a scaffolded project
  (``alloy.toml`` + ``CMakeLists.txt`` + ``src/main.cpp`` + …)
- **AND** ``.alloy/toolchain.lock`` SHALL pin every required
  non-vendor tool from the stm32g0 family
- **AND** the toolchain store under ``ALLOY_TOOLS_ROOT`` SHALL
  contain the matching extractions
- **AND** the command SHALL exit 0 with a "next steps" panel
  naming ``alloy build``

#### Scenario: setup inside a project skips scaffolding and installs

- **WHEN** the user runs ``alloy setup --auto`` inside a project
  whose ``alloy.toml`` resolves to ``stm32g0``
- **THEN** the scaffold step SHALL be skipped (no overwrite of
  existing project files)
- **AND** the install step SHALL run, populating
  ``.alloy/toolchain.lock``
- **AND** the run SHALL succeed even when the lockfile is partial
  (additive update for missing tools only)

#### Scenario: setup with --auto in CI never prompts

- **WHEN** ``alloy setup --auto --project-dir <path>`` is run
  with STDIN closed
- **THEN** no prompt SHALL be issued
- **AND** the run SHALL complete with the default answers

#### Scenario: setup with --no-tui falls back to the line prompt

- **WHEN** the user runs ``alloy setup --no-tui`` in a TTY
- **THEN** the family picker SHALL render as a line-based prompt
  (numbered list + ``> `` input)
- **AND** the install plan SHALL render as a Rich table without
  spawning a Textual app

#### Scenario: setup gracefully exits on Ctrl-C mid-prompt

- **WHEN** the user sends SIGINT during a wizard prompt
- **THEN** ``alloy setup`` SHALL exit with code 130
- **AND** the partial state (if any tools were installed before
  the cancel) SHALL remain in the store
- **AND** the output SHALL surface the partial-progress summary

## MODIFIED Requirements

### Requirement: alloy-cli SHALL scaffold projects via `alloy new`

The ``alloy new <NAME>`` command SHALL produce a complete,
schema-valid alloy project tree from either a ``--board <id>`` or a
``--device <vendor>/<family>/<chip>`` argument.  The generated tree
SHALL include: ``alloy.toml``, ``CMakeLists.txt``, ``src/main.cpp``,
``README.md``, ``.gitignore``, and SHALL pre-populate the manifest
with sensible defaults from the chosen board (debug UART, default
clock profile, LED GPIO when available).  The command SHALL refuse
to scaffold into a non-empty directory unless ``--force`` is given.

After scaffolding completes, ``alloy new`` SHALL offer to install
the family's toolchain.  The decision is governed by:

- ``--install-toolchain`` — always install; overrides every
  default.
- ``--no-install-toolchain`` — never install; overrides every
  default.
- ``--auto`` — combine with the install path; suppress every
  interactive confirmation.
- Default behaviour: when STDIN is a TTY and no flag was given,
  print the install plan and prompt ``Install toolchain now?
  [Y/n]``.  When STDIN is non-TTY (CI / pipe) and no flag was
  given, skip the install.

In every code path — installed, skipped, declined — the
post-scaffold output SHALL include the next-step commands the
user should run, including the explicit
``alloy toolchain install`` reminder when the install was
skipped.

#### Scenario: alloy new --board nucleo_g071rb produces a buildable project

- **WHEN** the user runs ``alloy new firmware --board nucleo_g071rb``
  in an empty directory with STDIN non-TTY
- **THEN** a directory ``firmware/`` SHALL be created
- **AND** ``firmware/alloy.toml`` SHALL validate against
  ``schema/alloy_toml_v1_1.json``
- **AND** ``firmware/alloy.toml [board].id`` SHALL be
  ``"nucleo_g071rb"``
- **AND** running ``cmake -S firmware -B firmware/build`` SHALL exit 0

#### Scenario: alloy new without board or device fails clearly

- **WHEN** the user runs ``alloy new firmware`` with neither
  ``--board`` nor ``--device``
- **THEN** the command SHALL exit non-zero
- **AND** stderr SHALL list ``alloy boards`` and ``alloy devices`` as
  next-step suggestions

#### Scenario: alloy new refuses non-empty target

- **WHEN** the user runs ``alloy new firmware --board <id>`` and
  ``firmware/`` already contains any file
- **AND** ``--force`` is **not** specified
- **THEN** the command SHALL exit non-zero with a message naming
  the existing files

#### Scenario: --install-toolchain triggers post-scaffold install

- **WHEN** the user runs
  ``alloy new firmware --board nucleo_g071rb --install-toolchain
  --auto``
- **THEN** ``firmware/.alloy/toolchain.lock`` SHALL exist after
  the run
- **AND** the install plan SHALL be printed before the install
- **AND** every required non-vendor tool from stm32g0 SHALL be
  in the toolchain store
- **AND** vendor tools SHALL be skipped with their install_doc URL

#### Scenario: --no-install-toolchain skips the post-scaffold install

- **WHEN** the user runs
  ``alloy new firmware --board nucleo_g071rb --no-install-toolchain``
- **THEN** no toolchain install SHALL run
- **AND** ``firmware/.alloy/toolchain.lock`` SHALL NOT exist
- **AND** the output SHALL include
  ``Run `alloy toolchain install`` as the next step

#### Scenario: TTY default offers the prompt and respects N

- **WHEN** the user runs
  ``alloy new firmware --board nucleo_g071rb`` in a TTY
- **AND** answers ``n`` to the install prompt
- **THEN** no install SHALL run
- **AND** the next-step command SHALL be printed

### Requirement: alloy doctor SHALL support a non-interactive `--fix` mode

``alloy doctor --fix`` SHALL run every available auto-fixer in
sequence and report a summary of outcomes.  The fix surface SHALL
include:

- ``alloy-devices-yml`` — git submodule init.
- ``mcp`` — pip install ``alloy-cli[mcp]``.
- ``toolchain:<tool-name>`` — install a missing non-vendor
  toolchain entry through
  ``toolchain_orchestrator.install_family`` (Wave 3).  One
  synthetic fixer per missing required tool the family declares.

Vendor-source tools SHALL NEVER be auto-fixed; they remain
info-severity rows with their per-OS install_doc URL.  A failure
in one fixer SHALL NOT abort the others — every queued fixer
runs.  The ``_print_fix_summary`` table SHALL surface per-tool
outcomes (✓ installed / ✗ failed / dim "skipped — vendor"
rows).  The exit code SHALL be 0 when no error rows remain in
the post-fix re-scan, and 1 otherwise.

The behaviour SHALL be additive: a project without a resolvable
family keeps today's two-fixer surface.  Adding the toolchain
fixer never blocks the existing ``--fix`` path.

#### Scenario: doctor --fix installs missing required tools for stm32g0

- **WHEN** the user runs ``alloy doctor --fix`` in a stm32g0
  project where arm-none-eabi-gcc, cmake, ninja, probe-rs are all
  missing
- **AND** the toolchain store starts empty
- **THEN** the four required tools SHALL be installed in sequence
- **AND** ``.alloy/toolchain.lock`` SHALL pin all four
- **AND** STM32CubeProgrammer (recommended, vendor) SHALL render
  as info — never as a failure, never as an attempted install

#### Scenario: doctor --fix reports per-tool failures without aborting

- **WHEN** ``alloy doctor --fix`` is run and the second tool's
  install raises ``family-toolchain-installer-checksum``
- **THEN** the first tool's outcome SHALL be ``installed``
- **AND** the second tool's outcome SHALL be ``failed`` with
  the typed error_type
- **AND** the third tool SHALL still be attempted

#### Scenario: doctor --fix without a resolvable family preserves today's behaviour

- **WHEN** ``alloy doctor --fix`` is run outside any project AND
  without ``--for``
- **THEN** the legacy fixers (submodule init, MCP install) SHALL
  still run
- **AND** no toolchain auto-fix SHALL be queued
- **AND** the output SHALL match the pre-Wave-3 baseline
