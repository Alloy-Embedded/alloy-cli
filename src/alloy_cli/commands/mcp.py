"""``alloy mcp serve`` — boot the MCP server adapter."""

from __future__ import annotations

from pathlib import Path

import click


@click.group("mcp", help="Model Context Protocol integrations.")
def mcp_command() -> None:
    """``alloy mcp <subcommand>``."""


@mcp_command.command("serve", help="Run the alloy MCP server (stdio default).")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http", "sse"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help="Transport for the MCP server.  HTTP / SSE land with the official SDK.",
)
@click.option(
    "--cwd",
    "project_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project directory exposed to MCP tools.",
)
def serve_command(transport: str, project_dir: Path) -> None:
    if transport.lower() != "stdio":
        raise click.ClickException(
            f"Transport {transport!r} requires `pip install alloy-cli[mcp]` and the "
            "official MCP SDK.  Use --transport stdio for the bundled fallback."
        )
    from alloy_cli.mcp.server import run_stdio

    run_stdio(project_dir=project_dir)


__all__ = ["mcp_command"]
