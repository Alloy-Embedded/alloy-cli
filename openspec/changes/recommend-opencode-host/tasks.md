# Tasks — recommend-opencode-host

## Phase 1: Config bundle

- [ ] 1.1 `src/alloy_cli/integrations/opencode/mcp_servers.json` —
      registers `alloy mcp serve` as MCP server.
- [ ] 1.2 `src/alloy_cli/integrations/opencode/system_prompt.md` —
      alloy-tuned system prompt covering tool-use patterns.
- [ ] 1.3 `src/alloy_cli/integrations/opencode/agents/firmware.json`
      — opencode agent definition for firmware work.

## Phase 2: `alloy chat` command

- [ ] 2.1 `cli.chat` Click command.
- [ ] 2.2 Detects opencode binary; launches it with
      `--mcp-config <our bundle>` and our system prompt.
- [ ] 2.3 If opencode missing: prints OS-specific install snippet
      and exits 2.
- [ ] 2.4 `--client claude-code` and `--client cursor` flags emit
      the corresponding config snippet for that client and exit 0
      (so users can paste into their existing config).

## Phase 3: Documentation

- [ ] 3.1 `docs/AI_INTEGRATION.md` covering opencode (primary),
      Claude Code, Cursor, Continue, Cline.
- [ ] 3.2 README "Quick AI demo" section: 3-line example +
      screenshot/asciinema link.
- [ ] 3.3 Tutorial: "Your first AI-driven blink" — 5-step doc
      from `alloy new` to flashed firmware via natural language.

## Phase 4: Smoke tests

- [ ] 4.1 `tests/integration/test_chat.py` — mocks an MCP client,
      issues 3 canonical prompts ("blink the LED", "add a debug
      UART", "what UARTs are available?"), asserts the expected
      tool-call sequence.
- [ ] 4.2 Test runs without an actual LLM (pre-recorded
      tool-call traces).

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/ai-integration/spec.md`.
- [ ] 5.2 `openspec validate recommend-opencode-host --strict`
      passes.
- [ ] 5.3 Manual end-to-end test against opencode + Anthropic
      Claude (gated test with `pytest.mark.requires_anthropic_key`).
