# Add MCP Server

## Why

The Model Context Protocol is the open standard that lets LLM agents
(Claude Code, opencode, Cursor, Continue, …) call **typed tools**
exposed by an external server.  Exposing alloy as an MCP server
means **every LLM client speaks alloy without per-client integration
code**.

This is the deliberate non-build of a custom AI agent.  We do not
write our own LLM loop, prompt management, model abstraction, or
TUI chat — opencode and Claude Code already do that well.  We
expose **typed, IR-grounded tools**; the agent is someone else's
problem.

## What Changes

- **`alloy mcp serve`** — new CLI subcommand starting an MCP server
  on stdio (default) or HTTP/SSE (`--transport http`).
- **Tools exposed** (one Python function each in
  `src/alloy_cli/mcp/tools.py`):

  ```
  alloy.list_boards(filter?) -> BoardSummary[]
  alloy.list_devices(filter?) -> DeviceSummary[]
  alloy.query_device_ir(device, peripheral_class?, fields?) -> IRView
  alloy.suggest_pins(device, peripheral, signal) -> PinCandidate[]
  alloy.suggest_dma(device, peripheral, direction) -> DmaCandidate[]
  alloy.read_alloy_toml() -> ProjectConfig
  alloy.preview_diff(operation, **args) -> UnifiedDiff
  alloy.add_uart(name, peripheral?, tx?, rx?, dma?, baud?) -> AppliedDiff
  alloy.add_gpio(name, pin, mode, label?, pull?, initial?) -> AppliedDiff
  alloy.add_spi(...) -> AppliedDiff
  alloy.add_i2c(...) -> AppliedDiff
  alloy.add_timer(...) -> AppliedDiff
  alloy.add_pwm(...) -> AppliedDiff
  alloy.add_adc(...) -> AppliedDiff
  alloy.set_clock_profile(profile) -> AppliedDiff
  alloy.build() -> BuildResult
  alloy.flash(probe?) -> FlashResult
  alloy.list_recent_events() -> EventLogEntry[]
  ```

- Every `add_*` and `set_*` tool is **transactional with confirm**:
  default behaviour returns the diff; the LLM must call
  `alloy.apply_diff(diff_id)` (or pass `--apply=true`) for the
  mutation to land.  This matches MCP best practice of "preview
  before write" and lets the LLM build a confidence chain.
- **Tool descriptions** are written for an LLM audience: explicit
  about preconditions, postconditions, side effects.  Living in
  Python docstrings consumed by the MCP SDK's tool-discovery
  layer.
- **Error model**: typed errors (`PinInvalidError`, `DmaConflictError`,
  `BoardNotFoundError`) so the LLM can disambiguate failure modes.

## Impact

A user with Claude Code, opencode, or Cursor can:

1. Configure their MCP client to launch `alloy mcp serve` (one-time
   step; `recommend-opencode-host` ships the recipe).
2. Open their chat; the LLM auto-discovers every tool.
3. Type `"blink the LED"` and watch the LLM call
   `list_boards → query_device_ir → suggest_pins → add_gpio →
   add_uart → preview_diff → apply_diff → build → flash`.

Every step is grounded in real IR data and validated.
Hallucinations become detection: if the LLM picks an invalid pin,
`add_gpio` returns a typed error that the LLM reads and corrects.

## What this DOES NOT do

- No bundled LLM model — bring your own (Anthropic / OpenAI /
  Ollama / Gemini handled by the LLM client).
- No bespoke `alloy chat` TUI — that's `recommend-opencode-host`.
- No sandboxing.  The MCP server has the same filesystem access as
  the user.  We rely on the diff-preview pattern for safety.
- No HTTP authentication beyond MCP's transport-layer auth.  Local
  stdio is the recommended deployment.
