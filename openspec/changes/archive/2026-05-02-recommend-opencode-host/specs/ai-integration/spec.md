## ADDED Requirements

### Requirement: alloy-cli SHALL ship an opencode integration recipe

`alloy-cli` SHALL bundle an MCP configuration, system prompt, and
agent definition compatible with **opencode** as the recommended
LLM host.  The `alloy chat` convenience command SHALL launch
opencode against the alloy MCP server with the bundled
configuration.  The bundle SHALL also be emittable for **Claude
Code**, **Cursor**, **Continue**, and **Cline** via
`alloy chat --client <name>`, which prints the configuration
snippet for the user to paste into their existing setup.

#### Scenario: alloy chat launches opencode with our config

- **WHEN** the user has opencode installed and runs `alloy chat`
  inside a configured project
- **THEN** opencode SHALL launch with the alloy MCP server
  registered as an MCP source
- **AND** opencode SHALL load our alloy-tuned system prompt
- **AND** typing a firmware prompt (e.g., "blink the LED") SHALL
  invoke the `alloy.list_boards → suggest_pins → add_gpio →
  build` tool sequence

#### Scenario: alloy chat without opencode prints install hint

- **WHEN** opencode is not on `PATH`
- **AND** the user runs `alloy chat`
- **THEN** the command SHALL exit non-zero
- **AND** stderr SHALL include the OS-specific install command
  (e.g., `brew install sst/tap/opencode`)
- **AND** SHALL link to `docs/AI_INTEGRATION.md` for alternative
  clients

#### Scenario: alloy chat --client cursor emits config snippet

- **WHEN** the user runs `alloy chat --client cursor`
- **THEN** the command SHALL print the Cursor-flavoured MCP
  configuration JSON to stdout
- **AND** SHALL exit 0 without launching anything
- **AND** the user SHALL be able to paste it into Cursor's
  settings to enable the alloy integration
