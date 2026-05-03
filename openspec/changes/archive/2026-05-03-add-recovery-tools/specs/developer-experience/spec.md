## ADDED Requirements

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
