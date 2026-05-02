## ADDED Requirements

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
