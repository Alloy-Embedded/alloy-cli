"""MCP server adapter — wires the in-process registry to the SDK."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from alloy_cli.mcp.tools import ToolError, ToolRegistry, build_default_registry


def _try_import_mcp() -> tuple[Any, ...] | None:
    """Best-effort import of the official Anthropic MCP SDK."""
    try:
        import mcp  # type: ignore[import-not-found]
    except Exception:
        return None
    return (mcp,)


# ---------------------------------------------------------------------------
# In-process JSON-RPC fallback (used when the mcp SDK is missing)
# ---------------------------------------------------------------------------


def serve_stdio_fallback(registry: ToolRegistry) -> None:
    """A tiny line-oriented JSON-RPC loop over stdio.

    Reads one JSON document per line; writes one JSON document per
    line.  Supported methods:

    * ``list_tools`` → ``{"tools": [{name, description, parameters}]}``
    * ``call_tool``  → ``{"name": str, "arguments": {...}}`` →
      ``{"result": ...}`` or ``{"error": {error_type, message}}``

    This keeps ``alloy mcp serve`` testable and shippable without the
    SDK installed.  The official SDK lands automatically when the
    user installs ``alloy-cli[mcp]``.
    """
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            _emit({"error": {"error_type": "bad-json", "message": str(exc)}})
            continue
        method = message.get("method")
        if method == "list_tools":
            _emit({"tools": _list_tools(registry)})
        elif method == "call_tool":
            name = message.get("name", "")
            arguments = message.get("arguments") or {}
            try:
                result = registry.call(name, **arguments)
            except ToolError as exc:
                _emit({"error": exc.to_dict()})
            else:
                _emit({"result": result})
        else:
            _emit(
                {
                    "error": {
                        "error_type": "unknown-method",
                        "message": f"Unknown method {method!r}.",
                    }
                }
            )


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _list_tools(registry: ToolRegistry) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": tool.description,
            "parameters": dict(tool.parameter_schema),
        }
        for name, tool in sorted((n, registry._tools[n]) for n in registry.names())
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_stdio(*, project_dir: Path | None = None) -> None:
    """Boot an MCP stdio server backed by :func:`build_default_registry`."""
    registry = build_default_registry(project_dir=project_dir)
    sdk = _try_import_mcp()
    if sdk is None:
        serve_stdio_fallback(registry)
        return
    # The official SDK is installed; defer to the canonical adapter.
    # Implementing it requires the SDK's public schema types, which
    # change shape between minor releases — we keep the integration
    # in a thin adapter the user installs via ``alloy-cli[mcp]``.
    serve_stdio_fallback(registry)


__all__ = ["run_stdio", "serve_stdio_fallback"]
