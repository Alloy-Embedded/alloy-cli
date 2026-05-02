# AI integration

`alloy-cli` exposes its operations as **typed MCP tools** so any
[Model Context Protocol]-compliant LLM client can drive your
firmware project.  This document covers the recommended host
([opencode]) plus integration recipes for Claude Code, Cursor,
Continue, and Cline.

[Model Context Protocol]: https://modelcontextprotocol.io
[opencode]: https://github.com/sst/opencode

## TL;DR

```sh
# 1. Install opencode (recommended)
brew install sst/tap/opencode          # macOS
curl -fsSL https://opencode.ai/install | bash   # Linux

# 2. Inside an alloy project, start chat
alloy chat
```

That's it.  `alloy chat` registers `alloy mcp serve` as opencode's
MCP source and loads the bundled system prompt.  Type
`"blink the LED"` and watch the agent call
`alloy.list_boards → suggest_pins → add_gpio → apply_diff →
build`.

## Why opencode

| Trait | Why it matters |
|-------|----------------|
| Open source (MIT) | Matches the alloy ecosystem licensing. |
| Provider-agnostic | Anthropic / OpenAI / Ollama / Gemini all work. |
| TUI-native | Pairs with `alloy ui` instead of a browser tab. |
| Active development | Frontier-tracking. |
| First-class MCP | The whole reason this proposal exists. |

## Other clients

`alloy chat --client <name>` prints the configuration snippet for
your existing tool — paste it into the client's settings to get
the same integration.

```sh
alloy chat --client claude-code   # → mcp_servers.json snippet
alloy chat --client cursor        # → settings.json fragment
alloy chat --client continue      # → mcpServers list entry
alloy chat --client cline         # → mcp_servers.json snippet
```

The `--print-config` flag does the same explicitly:

```sh
alloy chat --client opencode --print-config
```

## What the LLM sees

The bundled system prompt (run `alloy chat --print-prompt` to
see it verbatim) drills five operating principles:

1. **Always ground claims in the IR.**  Use `alloy.suggest_pins`
   and `alloy.query_device_ir` before guessing.
2. **Two-phase mutations.**  Every change goes through
   `preview_diff` → human review → `apply_diff`.
3. **Read typed errors.**  `PinInvalidError` / `instance-in-use`
   carry the source of truth, not your hunch.
4. **Respect existing peripherals.**  `read_alloy_toml` first.
5. **Build before declaring done.**  Always end with
   `alloy.build()` and surface the rc.

## Three canonical prompts

* **"Blink the LED."** → list_boards → query_device_ir →
  add_gpio → apply_diff → build.
* **"Add a debug UART for 115 200 baud on USART2."** →
  read_alloy_toml → suggest_pins(USART2.TX) →
  suggest_pins(USART2.RX) → add_uart → apply_diff → build.
* **"What UART instances are available on this chip?"** →
  query_device_ir(peripheral_class="uart").

## Manual setup (no `alloy chat`)

If you'd rather wire the MCP server up by hand, the canonical
configuration is:

```json
{
  "mcpServers": {
    "alloy": {
      "command": "alloy",
      "args": ["mcp", "serve"]
    }
  }
}
```

Drop this into the client's MCP-config location:

| Client | Path |
|--------|------|
| opencode | `~/.config/opencode/mcp_servers.json` |
| Claude Code | `~/.claude/mcp_servers.json` |
| Cursor | Settings → MCP servers |
| Continue | `~/.continue/config.json` (under `mcpServers`) |
| Cline | `~/.cline/mcp_servers.json` |
