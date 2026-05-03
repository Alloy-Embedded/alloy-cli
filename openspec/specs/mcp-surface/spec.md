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

