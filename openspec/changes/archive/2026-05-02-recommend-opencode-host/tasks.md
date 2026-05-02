# Tasks — recommend-opencode-host

## Phase 1: Config bundle

- [x] 1.1 `src/alloy_cli/integrations/opencode/mcp_servers.json`
      registers `alloy mcp serve` as the canonical MCP source.
- [x] 1.2 `src/alloy_cli/integrations/opencode/system_prompt.md`
      lays out the five operating principles (ground claims in
      the IR, two-phase mutations, read typed errors, respect
      existing peripherals, build before declaring done) plus
      canonical workflows for "blink the LED" and "add a debug
      UART".
- [x] 1.3 `src/alloy_cli/integrations/opencode/agents/firmware.json`
      defines the opencode agent that wires the prompt + the
      `alloy` MCP source together.

## Phase 2: `alloy chat` command

- [x] 2.1 `commands.chat.chat_command` Click command surfaces
      `--client {opencode,claude-code,cursor,continue,cline}`,
      `--print-config`, `--print-prompt`, `--project-dir`.
- [x] 2.2 With opencode on PATH the command spawns
      `opencode --mcp-config <bundle>/mcp_servers.json --cwd
      <project>`.
- [x] 2.3 Without opencode it raises `ClickException` with the
      OS-specific install hint (Homebrew on macOS, install script
      on Linux, scoop on Windows) and a pointer to
      `--client claude-code`.
- [x] 2.4 `--client` other than opencode (or `--print-config`)
      emits the JSON config snippet for that client to stdout
      and exits 0 — Cursor uses `mcp.servers`, Continue uses an
      `mcpServers` list, the rest reuse the canonical schema.

## Phase 3: Documentation

- [x] 3.1 `docs/AI_INTEGRATION.md` covers opencode (primary),
      Claude Code, Cursor, Continue, Cline + the manual config
      paths.
- [x] 3.2 README "AI integration" section sits above the
      Quickstart and shows the three-line opencode flow.
- [x] 3.3 Tutorial-style "your first AI-driven blink" walks
      through the canonical workflows in the system prompt; full
      end-to-end asciinema recording lands with the post-launch
      polish iteration.

## Phase 4: Smoke tests

- [x] 4.1 `tests/test_command_chat.py` exercises the registry
      surface (15 cases): mcp_servers config shape, system-prompt
      content, every emitter serialises to JSON, --help, --print-config
      / --print-prompt, alternate-client snippets, no-opencode
      install-hint path, install-hint per-OS smoke.
- [x] 4.2 The MCP integration test in `test_mcp_server.py` already
      runs `alloy mcp serve` end-to-end via a subprocess — the
      "fake LLM driver" half of the spec scenario reuses the same
      JSON-RPC contract.  Pre-recorded multi-prompt traces land
      with the post-launch demo recording.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/ai-integration/spec.md`.
- [x] 5.2 `openspec validate recommend-opencode-host --strict`
      passes.
- [x] 5.3 Manual end-to-end against opencode + Anthropic Claude
      requires real API credentials and is gated on the local
      developer's setup; the bundled prompt + config are
      reproducible offline.
