# mcp-surface Specification

## Purpose
TBD - created by archiving change add-mcp-server. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL expose a Model Context Protocol server

The `alloy mcp serve` command SHALL start an MCP-compliant server
exposing typed tools for read-only IR queries and transactional
project mutations.  The server SHALL support stdio transport (default,
recommended) and HTTP/SSE (`--transport http`).  Every tool SHALL
have an LLM-readable docstring describing purpose, preconditions,
postconditions, and side effects.  Mutating tools SHALL operate in
two phases (`preview_diff` → `apply_diff`) so the LLM client can
chain confirmation.

#### Scenario: MCP client discovers tools via stdio

- **WHEN** an MCP-compliant client (e.g., Claude Code or opencode)
  is configured with `command: alloy, args: [mcp, serve]`
- **AND** the client requests the tool list
- **THEN** the server SHALL return at least these tools:
  `list_boards`, `list_devices`, `query_device_ir`, `suggest_pins`,
  `suggest_dma`, `read_alloy_toml`, `preview_diff`, `apply_diff`,
  `add_uart`, `add_gpio`, `add_spi`, `add_i2c`, `set_clock_profile`,
  `build`, `flash`
- **AND** every tool SHALL have a non-empty `description` and
  typed parameter schema

#### Scenario: Mutating tool is transactional

- **WHEN** the client calls `alloy.add_uart(name="app", peripheral="USART1", tx="PA9", rx="PA10")`
- **THEN** the response SHALL include `diff_id`, the unified
  `diff_text`, and a `validation_summary`
- **AND** no filesystem mutation SHALL have occurred
- **AND** subsequent `alloy.apply_diff(diff_id)` SHALL atomically
  write the changes
- **AND** calling `apply_diff` after a 5-minute staleness window
  SHALL fail with `StaleDiffError`

#### Scenario: Invalid input returns typed error

- **WHEN** the client calls `alloy.add_gpio(pin="PA999", mode="output")`
- **AND** PA999 does not exist on the configured device
- **THEN** the tool result SHALL be an MCP error with structured
  `error_type="PinInvalidError"` and a `valid_alternatives` array
  of legal pin names from the IR
- **AND** no diff SHALL be cached

### Requirement: the MCP server SHALL expose an `alloy.regenerate` tool

The `alloy.regenerate` MCP tool SHALL force a fresh codegen run
by delegating to `core.codegen.force_regenerate(...)`.  The tool
result SHALL include the codegen return code and the list of
files written; the cache stamp SHALL be updated on success.

#### Scenario: alloy.regenerate forces a codegen pass

- **WHEN** an MCP client calls `alloy.regenerate`
- **AND** alloy-codegen is installed in the active environment
- **THEN** the tool SHALL invoke `force_regenerate(...)` exactly
  once
- **AND** the response SHALL include `returncode=0` and a
  non-empty `written` list
- **AND** the next `alloy.build` call's `codegen_skipped` SHALL be
  True (the freshly-written stamp matches)

### Requirement: the MCP server SHALL expose ``alloy.toolchain_apply_install_plan``

``alloy mcp serve`` SHALL register a new mutating tool
``toolchain_apply_install_plan`` that complements Wave 2's
``toolchain_install_plan`` (read-only).  The tool's parameter
schema SHALL declare a single required ``family_id: string``
argument.

The handler SHALL dispatch through
``toolchain_orchestrator.install_family`` and return a JSON-friendly
payload of the same shape across calls:

```
{
  "family_id": "stm32g0",
  "host": {"os": "macos", "arch": "arm64"},
  "outcomes": [
    {"tool": "...", "version": "...", "sha256": "...",
     "skipped": false, "reason": "installed",
     "bytes_downloaded": 280123456,
     "store_path": "..."},
    {"tool": "STM32CubeProgrammer", "version": "...",
     "skipped": true, "reason": "vendor",
     "install_doc_url": "https://www.st.com/..."}
  ],
  "total_bytes_downloaded": 290000000,
  "lockfile_updated": true
}
```

Idempotency SHALL be preserved: re-calling the tool on a fully-
installed family returns every outcome with ``skipped=true,
reason="already-installed"`` and ``total_bytes_downloaded=0``.
Vendor tools SHALL surface with ``skipped=true, reason="vendor"``
and a populated ``install_doc_url``; the handler SHALL NEVER
spawn a download for them.

The MCP system prompt (``src/alloy_cli/integrations/opencode/
system_prompt.md``) SHALL document the two-phase contract:
agents call ``toolchain_install_plan`` first, surface the plan
to the user, get explicit confirmation, then call
``toolchain_apply_install_plan``.  The Wave 1 ``preview_diff →
apply_diff`` pattern is the precedent; the same operating
principle applies here.

Errors SHALL propagate via the typed envelope.  Wave-2's
``family-toolchain-installer-{checksum,download,extract,
locked,store-corrupt,version-mismatch,unsupported-host}``
flow up unchanged.  Wave 3's
``onboarding-cancelled`` SHALL NOT be raised here — the MCP
caller cannot mid-cancel; the tool runs to completion or fails
typed.

#### Scenario: apply_install_plan installs every non-vendor tool

- **WHEN** an MCP client calls
  ``alloy.toolchain_apply_install_plan(family_id="stm32g0")``
- **AND** the toolchain store is empty
- **THEN** the response SHALL list every required + recommended
  non-vendor tool with ``skipped=false, reason="installed"``
- **AND** each entry SHALL carry ``store_path`` (absolute) +
  ``bytes_downloaded`` (>0)
- **AND** ``total_bytes_downloaded`` SHALL be the sum of every
  entry's ``bytes_downloaded``
- **AND** ``lockfile_updated`` SHALL be true (the project has a
  fresh ``.alloy/toolchain.lock`` after the call)

#### Scenario: re-calling apply_install_plan is idempotent

- **WHEN** an MCP client calls ``apply_install_plan`` twice in a
  row on the same family
- **THEN** the second response SHALL list every entry with
  ``skipped=true, reason="already-installed"``
- **AND** ``total_bytes_downloaded`` SHALL be 0
- **AND** no network call SHALL be made on the second invocation
  (verifiable by swapping in an exploding downloader)

#### Scenario: vendor tool is reported, never installed

- **WHEN** an MCP client calls ``apply_install_plan(family_id=
  "stm32f4")``
- **THEN** ``STM32CubeProgrammer`` SHALL appear in ``outcomes``
  with ``skipped=true, reason="vendor"``
- **AND** the entry SHALL include ``install_doc_url``
- **AND** the install_doc_url SHALL be the per-active-OS URL
  from the family manifest's ``install_docs`` block
- **AND** the downloader SHALL NOT be invoked for that tool

#### Scenario: install failure surfaces a typed envelope

- **WHEN** an MCP client calls ``apply_install_plan`` and one
  tool's downloader returns a corrupt artefact
- **THEN** the corresponding outcome row SHALL carry
  ``skipped=false, reason="failed",
  error_type="family-toolchain-installer-checksum"``
- **AND** the rest of the walk SHALL still complete (other tools
  install successfully)
- **AND** ``lockfile_updated`` SHALL still be true (the lockfile
  reflects the tools that DID succeed)

#### Scenario: tool list includes apply_install_plan on discovery

- **WHEN** an MCP client requests the tool list via ``list_tools``
- **THEN** the returned set SHALL include
  ``toolchain_apply_install_plan``
- **AND** the parameter schema SHALL declare ``family_id``
  as required
- **AND** the description SHALL document the
  ``toolchain_install_plan → toolchain_apply_install_plan``
  preview/confirm pattern

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

