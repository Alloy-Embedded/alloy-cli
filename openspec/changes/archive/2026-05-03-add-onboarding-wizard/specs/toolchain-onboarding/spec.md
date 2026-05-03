## ADDED Requirements

### Requirement: alloy-cli SHALL ship a UI-free toolchain install orchestrator

The repo SHALL include a module
``alloy_cli.core.toolchain_orchestrator`` exposing a single public
function ``install_family(manifest, *, project_root, include_optional,
force, on_event, downloader) -> InstallReport``.  The function SHALL
walk the family manifest's required + (optionally) recommended +
optional tiers, dispatch every non-vendor entry through
``tool_sources.adapter_for(...)`` followed by
``toolchain_manager.install(...)``, update
``.alloy/toolchain.lock`` when ``project_root`` is provided, and
return a typed :class:`InstallReport` summarising the walk.

The function SHALL NOT touch ``input()``, ``sys.stdin``, ``Console``,
``Textual``, or any rendering code.  Progress SHALL be surfaced
exclusively through the ``on_event`` callback receiving frozen
``InstallEvent`` dataclasses (``ToolStarted``,
``ToolSkippedVendor``, ``ToolSkippedHostUnsupported``,
``ToolDownloaded``, ``ToolInstalled``, ``ToolFailed``).

The orchestrator SHALL be testable without a TTY and without
network — supplying a ``downloader=FakeDownloader(...)`` exercises
every code path.

#### Scenario: install_family walks every non-vendor tool through the manager

- **WHEN** ``install_family(manifest, project_root=tmp_path,
  downloader=fake_dl, on_event=collector.append)`` is called against
  a stm32g0 manifest where every tool has a fixture artefact pinned
- **THEN** the manager SHALL be invoked once per non-vendor tool
- **AND** the resulting :class:`InstallReport` SHALL list every
  tool with its outcome (``installed`` / ``skipped-vendor`` /
  ``skipped-already-installed``)
- **AND** ``.alloy/toolchain.lock`` SHALL be written with the
  ``(tool, version, sha256)`` triple per installed entry

#### Scenario: vendor tools never reach the downloader

- **WHEN** ``install_family`` is called against a manifest whose
  recommended list contains a ``source: vendor`` entry
- **AND** the supplied downloader is configured to raise on any
  ``fetch()`` call
- **THEN** the call SHALL succeed
- **AND** the vendor entry SHALL appear in the report with
  ``skipped=True, reason="vendor"`` and a populated
  ``install_doc_url``
- **AND** the downloader SHALL NOT have been invoked for that tool

#### Scenario: lockfile write is gated by project_root

- **WHEN** ``install_family(manifest, project_root=None, ...)`` is
  called (the ``--shared`` callsite)
- **THEN** no ``.alloy/toolchain.lock`` SHALL be written under any
  directory
- **AND** the report's ``lockfile_updated`` SHALL be False

#### Scenario: a tool failure does not abort the rest of the walk

- **WHEN** ``install_family`` is called against a manifest with
  three required tools, where the second tool's downloader returns a
  corrupt artefact
- **THEN** the first tool SHALL install successfully
- **AND** the second tool SHALL surface
  ``ToolFailed(error_type="family-toolchain-installer-checksum")``
- **AND** the third tool SHALL also be attempted (and either
  installed or surfaced with its own typed failure)
- **AND** the report SHALL list one ``installed`` + one ``failed``
  + one ``installed`` outcome in that order

### Requirement: ``OnboardingCancelledError`` SHALL be exported from the AlloyCliError hierarchy

``alloy_cli.core.errors`` SHALL export
``OnboardingCancelledError`` as a subclass of ``AlloyCliError``
with the stable ``error_type = "onboarding-cancelled"``.  Wave-3
entry points SHALL raise it when the user cancels mid-wizard
(Ctrl-C from a line prompt, ``Cancel`` button in the TUI), and
SHALL attach the partial outcomes to the exception so the caller
can report "X of Y tools installed before you cancelled."

#### Scenario: the cancellation error type is unique and cookbook-anchored

- **WHEN** the test suite walks every ``AlloyCliError`` subclass
- **THEN** ``OnboardingCancelledError.error_type`` SHALL equal
  ``"onboarding-cancelled"``
- **AND** the value SHALL not collide with any other class
- **AND** ``docs/ERROR_COOKBOOK.md`` SHALL include a matching
  ``## onboarding-cancelled`` anchor (enforced by
  ``scripts/check_error_cookbook.py``)

### Requirement: alloy-cli SHALL register a shared install orchestrator API for every Wave-3 entry point

Every Wave-3 entry point SHALL dispatch toolchain installs through
``toolchain_orchestrator.install_family``.  The five entry points
are: ``alloy new`` post-scaffold prompt, ``alloy doctor --fix``
toolchain auto-fixer, ``alloy setup``, the TUI ``OnboardingScreen``,
and the MCP ``alloy.toolchain_apply_install_plan`` tool.  No entry
point SHALL re-implement the tier walk, the vendor short-circuit,
the adapter dispatch, the manager dispatch, or the lockfile
update.

A regression test SHALL pin this contract by asserting that none
of the five entry-point modules import ``tool_sources.adapter_for``
or ``toolchain_manager.install`` directly — they go through
``toolchain_orchestrator`` only.  ``alloy toolchain install``
itself is exempt because it pre-dates the orchestrator and was
the original install caller; the test allows that one direct
usage and forbids the rest.

#### Scenario: every entry point routes through the orchestrator

- **WHEN** the contract test scans the AST of
  ``commands/new.py``, ``commands/setup.py``,
  ``tui/screens/onboarding.py``, and the MCP handler
  ``_tool_toolchain_apply_install_plan``
- **THEN** none of those modules SHALL contain a direct call to
  ``toolchain_manager.install`` or
  ``tool_sources.adapter_for``
- **AND** each of them SHALL import or reference
  ``toolchain_orchestrator``
