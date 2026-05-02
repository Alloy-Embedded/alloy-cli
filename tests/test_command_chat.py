"""Tests for ``alloy chat`` — opencode launcher + alternate-client emitters."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from alloy_cli.commands import chat as _chat
from alloy_cli.main import cli


def test_supported_clients_includes_expected_set() -> None:
    assert "opencode" in _chat.SUPPORTED_CLIENTS
    assert "claude-code" in _chat.SUPPORTED_CLIENTS
    assert "cursor" in _chat.SUPPORTED_CLIENTS


def test_mcp_servers_config_registers_alloy_mcp_serve() -> None:
    config = _chat.mcp_servers_config()
    assert "mcpServers" in config
    server = config["mcpServers"]["alloy"]
    assert server["command"] == "alloy"
    assert server["args"] == ["mcp", "serve"]


def test_system_prompt_mentions_two_phase_pattern() -> None:
    text = _chat.system_prompt()
    assert "preview_diff" in text
    assert "apply_diff" in text
    assert "alloy.toml" in text


@pytest.mark.parametrize(
    "emitter",
    [
        _chat.cursor_config,
        _chat.continue_config,
        _chat.cline_config,
        _chat.claude_code_config,
        _chat.opencode_config,
    ],
)
def test_emitters_serialise_to_json(emitter) -> None:
    payload = emitter()
    encoded = json.dumps(payload)
    assert "alloy" in encoded


def test_alloy_chat_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["chat", "--help"])
    assert result.exit_code == 0
    for flag in ("--client", "--print-config", "--print-prompt", "--project-dir"):
        assert flag in result.output


def test_alloy_chat_print_config_emits_alloy_block() -> None:
    result = CliRunner().invoke(cli, ["chat", "--client", "opencode", "--print-config"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "alloy" in payload["mcpServers"]


def test_alloy_chat_cursor_emits_dotted_settings_key() -> None:
    result = CliRunner().invoke(cli, ["chat", "--client", "cursor"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "mcp.servers" in payload
    assert "alloy" in payload["mcp.servers"]


def test_alloy_chat_continue_emits_list() -> None:
    result = CliRunner().invoke(cli, ["chat", "--client", "continue"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload["mcpServers"], list)


def test_alloy_chat_print_prompt_emits_system_text() -> None:
    result = CliRunner().invoke(cli, ["chat", "--print-prompt"])
    assert result.exit_code == 0
    assert "Operating principles" in result.output


def test_alloy_chat_no_opencode_returns_install_hint(monkeypatch) -> None:
    monkeypatch.setattr("alloy_cli.commands.chat.shutil.which", lambda _name: None)
    result = CliRunner().invoke(cli, ["chat", "--client", "opencode"])
    assert result.exit_code != 0
    assert "opencode is not on PATH" in result.output
    assert "alloy_cli" not in result.output.lower() or "install" in result.output.lower()


def test_install_hint_returns_non_empty_string() -> None:
    assert _chat.install_hint().strip()
