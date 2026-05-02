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

