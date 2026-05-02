"""Smoke test: ``alloy --help`` exits 0 and mentions the platform.

Spec scenario: bootstrap-alloy-cli/specs/cli-surface — "--help
describes the tool".
"""

from __future__ import annotations

from click.testing import CliRunner

from alloy_cli.main import cli


def test_help_flag_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Alloy embedded platform" in result.output


def test_short_help_flag_works() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-h"])
    assert result.exit_code == 0
    assert "Alloy embedded platform" in result.output


def test_no_args_prints_banner() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code == 0
    assert "alloy" in result.output.lower()
