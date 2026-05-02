"""``alloy chat`` — launch opencode with our MCP recipe (or emit alternate-client snippets)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

import click

SUPPORTED_CLIENTS = ("opencode", "claude-code", "cursor", "continue", "cline")


# ---------------------------------------------------------------------------
# Bundle locators
# ---------------------------------------------------------------------------


def _bundle_root() -> Path:
    return Path(str(resources.files("alloy_cli").joinpath("integrations").joinpath("opencode")))


def mcp_servers_config() -> dict[str, Any]:
    return json.loads((_bundle_root() / "mcp_servers.json").read_text(encoding="utf-8"))


def system_prompt() -> str:
    return (_bundle_root() / "system_prompt.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-client config emitters
# ---------------------------------------------------------------------------


def claude_code_config() -> dict[str, Any]:
    """Claude Code uses ``.claude/mcp_servers.json`` with the same schema."""
    return mcp_servers_config()


def cursor_config() -> dict[str, Any]:
    """Cursor reads MCP servers from its settings under a slightly different shape."""
    config = mcp_servers_config()
    return {"mcp.servers": config["mcpServers"]}


def continue_config() -> dict[str, Any]:
    return {"mcpServers": list(mcp_servers_config()["mcpServers"].values())}


def cline_config() -> dict[str, Any]:
    return mcp_servers_config()


def opencode_config() -> dict[str, Any]:
    return mcp_servers_config()


_EMITTERS = {
    "opencode": opencode_config,
    "claude-code": claude_code_config,
    "cursor": cursor_config,
    "continue": continue_config,
    "cline": cline_config,
}


# ---------------------------------------------------------------------------
# Install hints
# ---------------------------------------------------------------------------


def install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install sst/tap/opencode"
    if system == "Linux":
        return "curl -fsSL https://opencode.ai/install | bash"
    if system == "Windows":
        return "scoop bucket add sst https://github.com/sst/scoop-tap; scoop install opencode"
    return "See https://github.com/sst/opencode for install instructions."


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("chat", help="Launch opencode wired up to the alloy MCP server.")
@click.option(
    "--client",
    type=click.Choice(SUPPORTED_CLIENTS, case_sensitive=False),
    default="opencode",
    show_default=True,
    help="LLM client to launch / emit config for.",
)
@click.option(
    "--print-config",
    is_flag=True,
    default=False,
    help="Emit the MCP config snippet for the chosen client and exit (no launch).",
)
@click.option(
    "--print-prompt",
    is_flag=True,
    default=False,
    help="Emit the bundled system prompt to stdout and exit.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project directory passed to the MCP server's --cwd flag.",
)
def chat_command(
    client: str,
    print_config: bool,
    print_prompt: bool,
    project_dir: Path,
) -> None:
    if print_prompt:
        sys.stdout.write(system_prompt())
        return

    emitter = _EMITTERS.get(client)
    if emitter is None:
        raise click.ClickException(f"Unknown client {client!r}.")

    if print_config or client != "opencode":
        json.dump(emitter(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return

    if shutil.which("opencode") is None:
        raise click.ClickException(
            f"opencode is not on PATH.  Install it: {install_hint()}\n"
            "Run with --client claude-code (or cursor, continue, cline) to emit a "
            "config snippet for an existing client."
        )

    config_path = _bundle_root() / "mcp_servers.json"
    cmd = [
        "opencode",
        "--mcp-config",
        str(config_path),
        "--cwd",
        str(project_dir.resolve()),
    ]
    env = dict(os.environ)
    env.setdefault("ALLOY_PROJECT_DIR", str(project_dir.resolve()))
    raise SystemExit(subprocess.call(cmd, env=env))


__all__ = [
    "SUPPORTED_CLIENTS",
    "chat_command",
    "claude_code_config",
    "cline_config",
    "continue_config",
    "cursor_config",
    "install_hint",
    "mcp_servers_config",
    "opencode_config",
    "system_prompt",
]
