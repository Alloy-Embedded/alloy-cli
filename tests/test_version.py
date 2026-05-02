"""Smoke test: ``alloy --version`` prints a non-empty SemVer string.

Spec scenario: bootstrap-alloy-cli/specs/cli-surface — "pip install
registers the alloy command".
"""

from __future__ import annotations

from click.testing import CliRunner

from alloy_cli.main import cli


def test_version_flag_exits_zero_with_version_string() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0, result.output
    # "alloy <version>"
    parts = result.output.strip().split()
    assert len(parts) == 2
    assert parts[0] == "alloy"
    assert parts[1]  # non-empty version string
