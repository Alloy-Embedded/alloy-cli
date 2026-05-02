# Recommend opencode as the LLM Host

## Why

We exposed alloy as MCP tools (`add-mcp-server`).  MCP works with
**any** compliant client — Claude Code, opencode, Cursor, Continue,
Cline — but new users need a recommended starting point that "just
works".

We pick **opencode** as the recommended LLM host because:

- **Open source** (MIT, sst/opencode) — fits the ecosystem.
- **Provider-agnostic** — Anthropic, OpenAI, Ollama, Gemini, etc.
- **TUI-native** — matches our terminal-first vision.
- **Active development** — frontier-tracking.
- **MCP support** — first-class.

This proposal does not fork or bundle opencode.  It ships a
**recipe**: a config file, a system prompt tuned for alloy's IR
patterns, agent definitions, and an `alloy chat` shortcut.

## What Changes

- **`alloy chat [project_path]`** — convenience command.  Detects
  whether `opencode` is on PATH; if so, launches it with our MCP
  config.  If not, prints install instructions for the user's OS.
- **MCP config bundle** at `src/alloy_cli/integrations/opencode/`:
  - `mcp_servers.json` — registers `alloy mcp serve` as the
    `alloy` MCP server.
  - `system_prompt.md` — alloy-flavoured system prompt (when to
    use `query_device_ir`, when to call `suggest_pins`, the
    transactional `preview_diff → apply_diff` pattern,
    interpreting typed errors).
  - `agents/firmware.json` — opencode agent definition for
    embedded firmware tasks.
- **Documentation** at `docs/AI_INTEGRATION.md` covering:
  - Installation: `brew install sst/tap/opencode` (or per-OS).
  - Manual config for users who don't want `alloy chat` (Claude
    Code, Cursor, Continue, Cline recipes — all using the same
    MCP config).
  - Prompt examples: "blink the LED", "add a UART for debug",
    "what's the maximum I²C speed for this chip?".
- **Shipping smoke test**: `pytest tests/integration/test_chat.py`
  spawns a mock LLM client through MCP, runs three canonical
  prompts, asserts the tool-call sequence completes.

## Impact

A new user runs `alloy chat`, types `"blink the LED"`, gets
working firmware in under 30 seconds.  Existing users of Claude
Code / Cursor get the same behaviour by adding our MCP config to
their existing setup.

This is the **public-launch moment** of the AI story.  Up to here
we've built tools for power users; this is what gets demoed to a
new user in 30 seconds.

## What this DOES NOT do

- Does not fork or modify opencode.  We ship a recipe.
- Does not bundle a model provider.  Users supply their own.
- Does not implement `alloy chat` against any LLM directly — only
  via opencode (or compatible client).
- Does not lock alloy-cli to opencode.  MCP works elsewhere; we
  document Claude Code / Cursor / Continue paths too.
