"""MCP integration for alloy-cli.

The :mod:`tools` module exposes a transport-agnostic tool registry
that backs every read-only / mutating operation we want LLM agents
to call.  :mod:`server` adapts the registry to whatever MCP SDK
is installed (the official Anthropic ``mcp`` package is the
default) and ``alloy mcp serve`` boots it.
"""

from alloy_cli.mcp.tools import (
    DiffCache,
    Tool,
    ToolError,
    ToolRegistry,
    build_default_registry,
)

__all__ = [
    "DiffCache",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "build_default_registry",
]
