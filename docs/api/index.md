# API reference

Auto-generated from the in-repo docstrings.  Adding a new public
symbol to one of the allowlisted modules surfaces it on the next
site build.

The allowlist:

| Module | Role |
|---|---|
| [`alloy_cli.core.toolchain_orchestrator`](toolchain-orchestrator.md) | Wave 3 install walker — five entry points dispatch through this |
| [`alloy_cli.core.probe_orchestrator`](probe-orchestrator.md) | Wave 4 hardware-ops walker — `alloy reset` / `erase` / `monitor` |
| [`alloy_cli.core.toolchain_registry`](toolchain-registry.md) | Wave 1 family manifests + extends chain |
| [`alloy_cli.core.tool_sources`](tool-sources.md) | Wave 2 source adapters (xpack / GitHub / probe-rs / espressif) + Downloader Protocol |
| [`alloy_cli.core.errors`](errors.md) | Every `AlloyCliError` subclass with its stable `error_type` |
| [`alloy_cli.mcp`](mcp.md) | `ToolRegistry` + every `Tool` registered for the MCP transport |

Private symbols (names starting with `_`) are filtered out.  See
[`docs/concepts/`](../concepts/index.md) for the architectural
narrative; this page is the symbol-by-symbol reference.
