## ADDED Requirements

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
