# recovery-tools Specification

## Purpose
TBD - created by archiving change add-recovery-tools. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL register a shared probe orchestrator API for every Wave-4 entry point

Every Wave-4 entry point SHALL dispatch probe operations through
``alloy_cli.core.probe_orchestrator``.  The five entry points
(``alloy reset``, ``alloy erase``, ``alloy monitor``, the TUI
``DebugScreen`` action group + ``MonitorScreen``, and the four MCP
probe tools) SHALL share one walker so probe selection, binary
resolution, argv assembly, and the typed-error vocabulary live in
exactly one place.

The orchestrator SHALL expose:

- ``select_probe(*, hint, project_root)`` — selects a probe from
  the active host.  ``hint`` matches ``alloy flash``'s
  ``vid:pid:serial`` shape; ``None`` triggers single-attached
  detection.
- ``reset_target(probe, *, method, halt_after)`` — non-destructive;
  no preview tool.  Returns a frozen :class:`ResetReport`.
- ``plan_erase(probe, *, regions, project_root)`` — read-only;
  resolves region aliases via the device IR's flash bank
  descriptors.  Returns a frozen :class:`ErasePlan`.
- ``execute_erase(probe, plan)`` — destructive; consumes the plan
  the caller built via ``plan_erase``.  Returns a frozen
  :class:`EraseReport`.
- ``open_monitor(probe, *, port, baud, mode, on_event)`` —
  session-style; emits :class:`MonitorEvent` via the callback.

The module SHALL be UI-free: no ``input()``, ``Console``,
``Textual``, or ``sys.stdin`` reference.  An AST-based regression
test (``tests/test_probe_orchestrator.py::
test_orchestrator_module_is_ui_free``) SHALL pin the invariant.

The orchestrator SHALL define a ``Probe`` Protocol; a
``FakeProbe`` test seam (mirroring Wave 2's
``FakeDownloader``) SHALL allow every entry point to be tested
without real hardware.

#### Scenario: every entry point dispatches through the orchestrator

- **WHEN** the test suite scans ``commands/{reset,erase,monitor}.py``
  and ``tui/screens/{debug,monitor}.py`` and the MCP probe tool
  handlers
- **THEN** each file SHALL import from ``probe_orchestrator``
- **AND** no file SHALL spawn ``probe-rs`` / ``openocd`` via
  ``subprocess`` directly (the orchestrator owns the seam)

#### Scenario: orchestrator module is UI-free

- **WHEN** a contributor adds a Click / Rich / Textual /
  ``input()`` reference to ``probe_orchestrator.py``
- **THEN** the AST regression test SHALL fail with a clear
  message naming the offending construct

### Requirement: alloy-cli SHALL ship typed errors for every probe + erase failure mode

Stable ``error_type`` strings SHALL register in
``tests/test_errors_uniqueness.py`` and have anchors in
``docs/ERROR_COOKBOOK.md``:

- ``family-toolchain-probe-not-found``
- ``family-toolchain-probe-not-attached``
- ``family-toolchain-probe-multiple-attached``
- ``family-toolchain-probe-unauthorised``
- ``family-toolchain-erase-aborted``
- ``family-toolchain-erase-unsupported-region``
- ``family-toolchain-erase-confirmation-required``
- ``family-toolchain-erase-probe-failed``
- ``probe-operation-cancelled``

Each error class SHALL extend ``AlloyCliError`` with the matching
``error_type`` class attribute.  The error vocabulary SHALL be
documented in ``docs/RECOVERY.md``.

#### Scenario: every error_type is unique and reachable

- **WHEN** the uniqueness regression test enumerates every
  ``AlloyCliError`` subclass
- **THEN** each new Wave-4 ``error_type`` SHALL appear exactly once
- **AND** each SHALL appear as a kebab-case anchor in
  ``ERROR_COOKBOOK.md``

#### Scenario: vendor-only probe surfaces a typed error and a vendor-tool name

- **WHEN** the orchestrator detects a probe whose
  ``vendor_only`` flag is True (proprietary J-Link / locked
  ST-Link)
- **THEN** ``select_probe`` SHALL raise
  ``FamilyToolchainProbeUnauthorisedError``
- **AND** the error message SHALL name the vendor utility the
  user must install (J-Link Commander / STM32CubeProgrammer)
- **AND** the orchestrator SHALL NEVER auto-invoke the vendor tool

### Requirement: alloy-cli SHALL provide a Probe Protocol + FakeProbe test seam

The ``Probe`` Protocol SHALL define every operation the
orchestrator dispatches.  A ``FakeProbe`` implementation SHALL:

- Record every ``reset`` / ``erase`` / ``monitor`` call.
- Emit scripted ``MonitorEvent``s in tests.
- Allow tests to inject typed errors so failure paths are
  exercised end-to-end without real hardware.

Tests SHALL never import ``probe-rs`` / ``openocd`` binaries.  CI
SHALL run the entire Wave-4 suite against the ``FakeProbe`` seam.

#### Scenario: FakeProbe records reset calls

- **WHEN** a test calls ``orchestrator.reset_target(fake_probe,
  method="soft")``
- **THEN** ``fake_probe.reset_calls`` SHALL contain a
  ``ResetCall(method="soft", halt_after=False)``
- **AND** ``ResetReport`` SHALL be returned with the recorded
  ``ProbeIdentity``

### Requirement: alloy-cli SHALL document the recovery vocabulary

A new ``docs/RECOVERY.md`` SHALL cover:

- The three commands (``alloy reset``, ``alloy erase``,
  ``alloy monitor``) with worked examples.
- The shared orchestrator API (functions + dataclasses + Protocol).
- The two-phase pattern for ``alloy erase`` (CLI prompt; MCP
  ``probe_erase_plan`` → ``probe_erase`` with ``confirm=True``).
- The vendor-probe contract.
- The full error_type taxonomy with cross-links to the cookbook.
- Cross-links to ``TOOLCHAIN_ONBOARDING.md`` (Wave 3) and
  ``TOOLCHAIN_INSTALLER.md`` (Wave 2).

A regression test (``tests/test_recovery_doc.py``) SHALL assert
that every required error_type is named, every command has its
own subsection, and every cookbook anchor for relevant errors is
linked.

#### Scenario: the doc names every recovery error_type

- **WHEN** the test suite parses ``docs/RECOVERY.md``
- **THEN** the doc SHALL mention every Wave-4 ``error_type`` from
  the taxonomy

#### Scenario: the doc has a subsection for every command

- **WHEN** the test suite walks the doc's ``##`` / ``###``
  headers
- **THEN** there SHALL be a section for ``alloy reset``,
  ``alloy erase``, and ``alloy monitor``
- **AND** there SHALL be a section for the MCP two-phase pattern

