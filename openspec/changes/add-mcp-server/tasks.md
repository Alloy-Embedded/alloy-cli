# Tasks — add-mcp-server

## Phase 1: Server scaffold

- [ ] 1.1 Add `mcp>=0.10` to `[project.optional-dependencies] mcp`.
- [ ] 1.2 `src/alloy_cli/mcp/server.py` boots an MCP server with
      stdio transport.
- [ ] 1.3 `cli.mcp.serve` Click command wraps it.  Flags:
      `--transport stdio|http|sse`, `--port`, `--cwd`.
- [ ] 1.4 Tool registration via `@register_tool(...)` decorator
      that wraps a `core/` operation, generating MCP tool schema
      from the Python type signature + docstring.

## Phase 2: Read-only tools

- [ ] 2.1 `alloy.list_boards(filter?)` → wraps
      `core.search.boards.search`.
- [ ] 2.2 `alloy.list_devices(filter?)` → wraps
      `core.search.devices.search`.
- [ ] 2.3 `alloy.query_device_ir(device, peripheral_class?,
      fields?)` → narrow IR view (pin candidates, DMA routes,
      clock graph, etc.)
- [ ] 2.4 `alloy.suggest_pins(device, peripheral, signal)` →
      `core.suggestions.suggest_pins`.
- [ ] 2.5 `alloy.suggest_dma(device, peripheral, direction)` →
      `core.suggestions.suggest_dma`.
- [ ] 2.6 `alloy.read_alloy_toml()` → `core.project.read`.
- [ ] 2.7 `alloy.list_recent_events()` → tail of
      `.alloy/cache/events.jsonl`.

## Phase 3: Mutating tools (transactional)

- [ ] 3.1 `alloy.preview_diff(op, **args)` →
      `core.peripherals.add_*` returning `(diff_id, diff_text)`.
      Caches diff in process memory.
- [ ] 3.2 `alloy.add_uart(...)` etc. → return
      `(diff_id, diff_text, validation_summary)`.
- [ ] 3.3 `alloy.apply_diff(diff_id)` → looks up diff, writes
      atomically.  Refuses if diff is older than 5 minutes (avoids
      stale-state apply).
- [ ] 3.4 `alloy.set_clock_profile(profile)` →
      `core.clocks.set_profile`.
- [ ] 3.5 `alloy.build()` → `core.build.run`.  Streams progress
      via MCP streaming-response.
- [ ] 3.6 `alloy.flash(probe?)` → `core.flash.run`.

## Phase 4: Error model

- [ ] 4.1 Typed error hierarchy: `AlloyMcpError`,
      `DeviceNotFoundError`, `PinInvalidError`,
      `DmaConflictError`, `ToolchainMissingError`, …
- [ ] 4.2 MCP tool-call result includes structured error fields so
      LLMs can branch on type, not parse English.

## Phase 5: Tool descriptions

- [ ] 5.1 Every tool has a docstring with: purpose, preconditions,
      side effects, examples.  These ARE the prompts the LLM
      sees.
- [ ] 5.2 `mcp.descriptions` test asserting every public tool has
      a non-empty docstring.

## Phase 6: Tests

- [ ] 6.1 In-process MCP client harness for every tool.
- [ ] 6.2 End-to-end test: spin up server in subprocess, fake LLM
      driver issues `list_boards → suggest_pins → preview_diff →
      apply_diff → build`, asserts each step succeeds.
- [ ] 6.3 Hallucination defence test: client requests
      `add_gpio(pin="PA999")`; server returns typed
      `PinInvalidError` with valid alternatives.

## Phase 7: Spec + final checks

- [ ] 7.1 Spec deltas in `specs/mcp-surface/spec.md`.
- [ ] 7.2 `openspec validate add-mcp-server --strict` passes.
- [ ] 7.3 README "AI integration" section linking to opencode
      recipe.
