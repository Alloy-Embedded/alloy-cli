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

### Requirement: alloy-cli SHALL document the four onboarding entry points

The repo SHALL include ``docs/TOOLCHAIN_ONBOARDING.md`` covering:

- The four user-facing entry points (``alloy new --install-toolchain``,
  ``alloy doctor --fix``, ``alloy setup``, the TUI Onboarding
  screen) and a decision matrix for "which one do I reach for?"
- The shared orchestrator API (``install_family`` signature,
  ``InstallEvent`` event class, ``InstallReport`` shape) for
  contributors authoring new entry points.
- The two-phase MCP pattern (``toolchain_install_plan →
  toolchain_apply_install_plan``) with a worked example of how
  an LLM agent should structure the call.
- The vendor-tool contract (vendor tools NEVER auto-install;
  install_doc URLs surface across all five surfaces).
- The cancellation contract (``OnboardingCancelledError``,
  exit-130 mapping, partial-outcome semantics).
- Cross-links to ``docs/TOOLCHAIN_REGISTRY.md`` (Wave 1) and
  ``docs/TOOLCHAIN_INSTALLER.md`` (Wave 2).

The doc SHALL include a regression test (``tests/test_toolchain_
onboarding_doc.py``) asserting that every required ``InstallEvent``
type is namedropped, every entry point has its own subsection, and
every cookbook anchor for relevant errors is linked.

#### Scenario: the doc names every InstallEvent class

- **WHEN** the test suite parses
  ``docs/TOOLCHAIN_ONBOARDING.md``
- **THEN** the doc SHALL mention every event class name
  (``ToolStarted``, ``ToolDownloaded``, ``ToolInstalled``,
  ``ToolFailed``, ``ToolSkippedVendor``,
  ``ToolSkippedHostUnsupported``)

#### Scenario: the doc has a subsection for every entry point

- **WHEN** the test suite walks the doc's ``##`` headers
- **THEN** there SHALL be a section for ``alloy new``,
  ``alloy doctor --fix``, ``alloy setup``, the TUI Onboarding
  screen, and ``alloy.toolchain_apply_install_plan``

#### Scenario: the doc documents the cancellation contract

- **WHEN** the test suite searches for the cancellation anchor
- **THEN** the doc SHALL include the string
  ``onboarding-cancelled``
- **AND** SHALL link to
  ``ERROR_COOKBOOK.md#onboarding-cancelled``

### Requirement: ``docs/QUICKSTART.md`` SHALL use the install-toolchain flow

The QUICKSTART SHALL be rewritten so the canonical "five-minutes
to first ELF" path uses the post-scaffold install prompt rather
than the explicit ``alloy toolchain install`` step:

```sh
pip install alloy-cli
alloy new firmware --board nucleo_g071rb     # answer Y when prompted
cd firmware
alloy build
alloy flash
```

The doc SHALL clarify that:

- The post-scaffold prompt downloads ~290 MB across 5-6 tools
  for the stm32g0 family.
- Vendor tools (STM32CubeProgrammer) are NOT installed
  automatically and the doc points the user at the install_doc
  URL when relevant for their workflow.
- ``--no-install-toolchain`` is the escape hatch for users who
  manage their toolchain externally (system arm-gcc, conda env,
  Docker container).
- ``alloy doctor --fix`` is the recommended "I cloned an existing
  project and need everything" command.

The smoke test asserts every command block in the QUICKSTART
exists in the live Click tree (existing developer-experience
contract) — Wave 3 doesn't change that test, only the doc body.

#### Scenario: the QUICKSTART references the install-toolchain flow

- **WHEN** the test suite parses ``docs/QUICKSTART.md``
- **THEN** the doc SHALL mention ``--install-toolchain`` (or the
  default-Y interactive prompt)
- **AND** SHALL include ``alloy doctor --fix`` as the
  "existing project" path
- **AND** SHALL link to ``TOOLCHAIN_ONBOARDING.md`` for the
  full reference

### Requirement: alloy-cli SHALL document the recovery flow

The repo SHALL include ``docs/RECOVERY.md`` covering:

- Worked examples for ``alloy reset``, ``alloy erase``, and
  ``alloy monitor``.
- The shared orchestrator API
  (``select_probe`` / ``reset_target`` / ``plan_erase`` /
  ``execute_erase`` / ``open_monitor``) for contributors
  authoring new entry points.
- The two-phase MCP pattern for ``alloy.probe_erase`` (preview
  via ``probe_erase_plan``, apply via ``probe_erase`` with
  ``confirm=true``) with a worked example.
- The vendor-probe contract (vendor-only probes surface
  ``family-toolchain-probe-unauthorised``; never auto-invoked).
- The cancellation contract (``ProbeOperationCancelledError``,
  graceful close on Ctrl+], byte count + duration summary).
- The full Wave-4 error vocabulary with cookbook anchors.
- Cross-links to ``TOOLCHAIN_ONBOARDING.md`` (Wave 3) and
  ``TOOLCHAIN_INSTALLER.md`` (Wave 2).

The doc SHALL include a regression test
(``tests/test_recovery_doc.py``) asserting that every required
``error_type`` is namedropped, every command has its own
subsection, and every cookbook anchor is linked.

#### Scenario: the doc names every recovery error_type

- **WHEN** the test suite parses ``docs/RECOVERY.md``
- **THEN** the doc SHALL mention every Wave-4 ``error_type``
  (``family-toolchain-probe-{not-found,not-attached,
  multiple-attached,unauthorised}``;
  ``family-toolchain-erase-{aborted,unsupported-region,
  confirmation-required,probe-failed}``;
  ``probe-operation-cancelled``)

#### Scenario: the doc has a subsection per command

- **WHEN** the test suite walks the doc's ``##`` / ``###``
  headers
- **THEN** there SHALL be a section for ``alloy reset``,
  ``alloy erase``, ``alloy monitor``, and the MCP two-phase
  pattern

#### Scenario: the doc links every error to the cookbook

- **WHEN** the test suite scans for cookbook anchors
- **THEN** every Wave-4 ``error_type`` SHALL appear as a
  ``ERROR_COOKBOOK.md#<error_type>`` link

### Requirement: ``docs/QUICKSTART.md`` SHALL gain a recovery example

The QUICKSTART SHALL include a brief addendum after the build /
flash steps showing:

```sh
alloy reset
alloy monitor             # press Ctrl+] to disconnect
```

The doc SHALL clarify that:

- ``alloy reset`` is non-destructive — the firmware on the chip
  stays put.
- ``alloy monitor`` auto-detects the debug UART from
  ``alloy.toml``.
- ``alloy erase`` exists for recovery from a brick but is gated
  behind a confirmation prompt.

#### Scenario: the QUICKSTART references the recovery commands

- **WHEN** the test suite parses ``docs/QUICKSTART.md``
- **THEN** the doc SHALL mention ``alloy reset``,
  ``alloy monitor``, and ``alloy erase``
- **AND** SHALL link to ``RECOVERY.md`` for the full reference

### Requirement: alloy-cli SHALL expose a `[docs]` install extra

The `pyproject.toml` SHALL declare an optional-dependencies group
named `docs` that lists every dependency required to build the
documentation site (mkdocs, mkdocs-material, mkdocstrings[python],
mkdocs-click, mkdocs-redirects, mkdocs-include-markdown-plugin,
pymdown-extensions).  Contributors SHALL be able to install the
build prerequisites with `pip install -e .[docs]`.

#### Scenario: `pip install -e .[docs]` resolves every doc-build dep

- **WHEN** a contributor runs `pip install -e .[docs]` in a clean
  virtual environment
- **THEN** every dependency required by `mkdocs build --strict`
  SHALL be installed
- **AND** running `mkdocs --version` SHALL print a non-empty
  version string
- **AND** running `mkdocs build --strict` against the repo's
  `mkdocs.yml` SHALL succeed

#### Scenario: the runtime install does NOT pull doc-build deps

- **WHEN** a user runs `pip install alloy-cli` without extras
- **THEN** `mkdocs` SHALL NOT be installed
- **AND** `pip show alloy-cli | grep Requires` SHALL NOT list any
  doc-build dependency
- **AND** importing `alloy_cli` SHALL succeed without the docs
  extras

### Requirement: alloy-cli SHALL surface the public docs site as a contributor entry point

The `README.md` SHALL link to the deployed docs site
(`https://alloy-embedded.github.io/alloy-cli/`) as the canonical
"learn more" entry point.  Contributors landing on the GitHub
project page SHALL be able to reach the rendered site within one
click.

#### Scenario: the README links to the deployed docs site

- **WHEN** the test suite parses `README.md`
- **THEN** the file SHALL contain a link to the GitHub Pages URL
  for the project (`alloy-embedded.github.io/alloy-cli` or the
  configured custom domain)
- **AND** the link's anchor text SHALL be discoverable in the
  first 30 lines (top of the README, above the fold)

