## ADDED Requirements

### Requirement: alloy-cli SHALL expose ``alloy.probe_reset`` (idempotent)

The ``probe_reset`` MCP tool SHALL dispatch through
``probe_orchestrator.reset_target`` and return a JSON-friendly
``ResetReport`` projection.  Parameters:

- ``probe`` (string, optional) — ``vid:pid:serial`` selector.
  When omitted the tool uses single-attached detection.
- ``method`` (string, optional, default ``"soft"``) — ``"soft"``
  or ``"hard"``.
- ``halt_after`` (bool, optional, default ``false``).

The tool SHALL be idempotent + safe (reset is non-destructive); no
preview tool is required.  Errors propagate as the typed envelope:
``family-toolchain-probe-{not-attached, multiple-attached,
unauthorised, not-found}``.

The response SHALL carry ``probe`` (id + kind), ``method`` used,
``halt_after``, ``duration_ms``.

#### Scenario: probe_reset on a single-attached probe

- **WHEN** an agent calls ``probe_reset`` with no parameters
- **THEN** the tool SHALL return a JSON object with ``probe``,
  ``method="soft"``, ``halt_after=false``, ``duration_ms``
- **AND** SHALL be idempotent on a re-call

#### Scenario: probe_reset with no attached probe

- **WHEN** no probe is attached
- **THEN** the tool SHALL raise the typed envelope
  ``family-toolchain-probe-not-attached``
- **AND** the envelope SHALL carry an empty ``detected_probes``
  array

### Requirement: alloy-cli SHALL expose ``alloy.probe_erase_plan`` (read-only)

The ``probe_erase_plan`` MCP tool SHALL dispatch through
``probe_orchestrator.plan_erase`` and return a JSON-friendly
``ErasePlan`` projection — never executing an erase.  Parameters:

- ``probe`` (string, optional).
- ``regions`` (array of strings, optional).  Each entry is either
  a region alias (resolved via the device IR) or a
  ``0xBASE-0xEND`` literal range.

The response SHALL carry ``probe``, ``regions`` (resolved tuple
of ``{name, base, size}``), ``total_bytes``.  Unsupported region
names raise ``family-toolchain-erase-unsupported-region`` with
a list of known regions in the envelope.

#### Scenario: probe_erase_plan with no regions returns the chip-wide plan

- **WHEN** an agent calls ``probe_erase_plan`` with no
  ``regions`` parameter
- **THEN** the tool SHALL return a single-region plan covering
  the full flash (``name="all"``)

#### Scenario: probe_erase_plan with a known alias

- **WHEN** an agent calls ``probe_erase_plan`` with
  ``regions=["bootloader"]`` against a chip whose IR declares it
- **THEN** the tool SHALL return a one-region plan with the
  resolved ``base`` + ``size``

#### Scenario: probe_erase_plan with an unknown alias

- **WHEN** an agent calls ``probe_erase_plan`` with
  ``regions=["not-a-region"]``
- **THEN** the tool SHALL raise
  ``family-toolchain-erase-unsupported-region``

### Requirement: alloy-cli SHALL expose ``alloy.probe_erase`` (mutating, two-phase)

The ``probe_erase`` MCP tool SHALL execute the erase plan
through ``probe_orchestrator.execute_erase``.  Parameters:

- ``probe`` (string, optional).
- ``regions`` (array of strings, optional) — same shape as
  ``probe_erase_plan``.
- ``confirm`` (bool, **required**).  When omitted or ``false``
  the tool SHALL raise
  ``family-toolchain-erase-confirmation-required``.

Pattern: agents call ``probe_erase_plan`` first to preview,
surface the plan to the user, get explicit confirmation, then
call ``probe_erase`` with ``confirm=true``.

The response SHALL carry ``probe``, ``regions``, ``total_bytes_
erased``, ``duration_ms``.  Backend failures propagate as
``family-toolchain-erase-probe-failed`` with the underlying
probe-rs / openocd stderr in the envelope ``detail``.

#### Scenario: probe_erase without confirm fails fast

- **WHEN** an agent calls ``probe_erase`` without ``confirm``
  (or with ``confirm=false``)
- **THEN** the tool SHALL raise
  ``family-toolchain-erase-confirmation-required``
- **AND** the envelope SHALL include a hint message naming
  ``probe_erase_plan``

#### Scenario: probe_erase after a plan call succeeds

- **WHEN** an agent calls ``probe_erase_plan`` then
  ``probe_erase`` with ``confirm=true`` (and matching regions)
- **THEN** the tool SHALL execute the erase and return the
  ``EraseReport`` JSON projection

### Requirement: alloy-cli SHALL expose session-style ``alloy.probe_monitor_*`` tools

Three coordinated tools SHALL implement the monitor session:

- ``probe_monitor_open(probe, port, baud, mode)`` — opens a
  session; returns ``{session_id, started_at, probe}``.
- ``probe_monitor_poll(session_id)`` — returns
  ``{new_bytes, total_bytes, duration_ms, closed}``.
- ``probe_monitor_close(session_id)`` — closes the session;
  returns the final summary.

Sessions SHALL be tracked server-side keyed on UUID.  An idle
session (no ``poll`` for 5 minutes) SHALL auto-close so a crashed
agent does not leak threads.

The response from ``poll`` SHALL stream incrementally — each
call returns only the bytes that arrived since the previous
``poll``.  ``new_bytes`` SHALL be UTF-8 string with
``errors="replace"`` for non-UTF8 bytes.

Errors propagate as the typed envelope:
``probe-operation-cancelled`` (when the session times out or is
closed mid-poll).

#### Scenario: probe_monitor_open returns a session id

- **WHEN** an agent calls ``probe_monitor_open`` with a
  configured port
- **THEN** the tool SHALL return a JSON object with
  ``session_id`` (UUID), ``started_at``, ``probe``

#### Scenario: probe_monitor_poll surfaces incremental bytes

- **WHEN** an agent polls a session that received 30 bytes
  since the last poll
- **THEN** ``new_bytes`` SHALL contain those 30 bytes
- **AND** ``total_bytes`` SHALL be the cumulative count
- **AND** ``closed`` SHALL be ``false``

#### Scenario: probe_monitor_close closes a session cleanly

- **WHEN** an agent calls ``probe_monitor_close`` on an open
  session
- **THEN** the tool SHALL return ``{closed: true,
  total_bytes, duration_ms}``
- **AND** subsequent polls on the same id SHALL raise
  ``probe-operation-cancelled``

#### Scenario: probe_monitor session times out after 5 minutes idle

- **WHEN** an agent opens a session and never polls for 5+
  minutes
- **THEN** the session SHALL auto-close
- **AND** subsequent ``poll`` / ``close`` calls SHALL raise
  ``probe-operation-cancelled``

### Requirement: every Wave-4 MCP tool SHALL register in ``_PARAM_SCHEMA`` and the default registry

The four new tools SHALL appear in:

- ``_PARAM_SCHEMA`` with their typed parameter map.
- ``build_default_registry``'s handler dict.
- ``ToolRegistry.names()`` so MCP discovery surfaces them.

#### Scenario: probe tools are discoverable

- **WHEN** the test suite enumerates ``ToolRegistry.names()`` of
  the default registry
- **THEN** the result SHALL include ``probe_reset``,
  ``probe_erase_plan``, ``probe_erase``, ``probe_monitor_open``,
  ``probe_monitor_poll``, ``probe_monitor_close``
