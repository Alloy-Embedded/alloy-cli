"""Tests for ``add-quickstart-and-cookbook`` (#29)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core.project import PROJECT_FILE, read
from alloy_cli.main import cli

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES = _REPO_ROOT / "docs" / "EXAMPLES"
_QUICKSTART = _REPO_ROOT / "docs" / "QUICKSTART.md"
_COOKBOOK = _REPO_ROOT / "docs" / "ERROR_COOKBOOK.md"
_CHEATSHEET = _REPO_ROOT / "docs" / "CHEATSHEET.md"


# ---------------------------------------------------------------------------
# Quickstart + examples
# ---------------------------------------------------------------------------


def test_quickstart_walks_through_alloy_new() -> None:
    body = _QUICKSTART.read_text(encoding="utf-8")
    assert "alloy new" in body
    assert "alloy build" in body
    assert "alloy flash" in body


@pytest.mark.parametrize(
    "name", ("01-blinky", "02-uart-echo", "03-spi-flash", "04-dma-double-buffer")
)
def test_each_example_has_readme_and_alloy_toml(name: str) -> None:
    root = _EXAMPLES / name
    assert (root / "README.md").exists(), f"{name}/README.md missing"
    assert (root / PROJECT_FILE).exists(), f"{name}/alloy.toml missing"


@pytest.mark.parametrize(
    "name", ("01-blinky", "02-uart-echo", "03-spi-flash", "04-dma-double-buffer")
)
def test_each_example_alloy_toml_parses(name: str) -> None:
    config = read(_EXAMPLES / name / PROJECT_FILE)
    assert config.project.name
    assert config.board is not None or config.chip is not None


# ---------------------------------------------------------------------------
# alloy new --from-example
# ---------------------------------------------------------------------------


def test_alloy_new_help_advertises_from_example() -> None:
    result = CliRunner().invoke(cli, ["new", "--help"])
    assert result.exit_code == 0
    assert "--from-example" in result.output


def test_alloy_new_from_example_unknown_name(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli, ["new", "myproj", "--from-example", "999-nope", "--no-git"]
        )
    assert result.exit_code != 0
    assert "Unknown example" in result.output


def test_alloy_new_from_example_clashes_with_board(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "new",
                "myproj",
                "--board",
                "nucleo_g071rb",
                "--from-example",
                "01-blinky",
                "--no-git",
            ],
        )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_alloy_new_from_example_writes_renamed_alloy_toml(tmp_path: Path) -> None:
    # Seed a board catalogue so the scaffold can resolve nucleo_g071rb.
    from tests.snapshots._render import seed_board_catalog

    seed_board_catalog(tmp_path)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as work:
        result = runner.invoke(
            cli,
            [
                "new",
                "myblinky",
                "--from-example",
                "01-blinky",
                "--no-git",
                "--force",
            ],
        )
        assert result.exit_code == 0, result.output
        toml = Path(work) / "myblinky" / PROJECT_FILE
        assert toml.exists()
        config = read(toml)
        # Renamed; example's GPIO carried through.
        assert config.project.name == "myblinky"
        assert any(p.name == "led" for p in config.peripherals)


# ---------------------------------------------------------------------------
# Cheatsheet generator
# ---------------------------------------------------------------------------


def test_cheatsheet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "generate_cheatsheet.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_cheatsheet_includes_every_top_level_command() -> None:
    body = _CHEATSHEET.read_text(encoding="utf-8")
    # `alloy add` is a Click group — leaves like `alloy add uart`
    # are what the cheatsheet enumerates.  Pick a representative
    # subset that any breakage would surface.
    for sub in ("alloy add uart", "alloy build", "alloy boards", "alloy doctor"):
        assert f"`{sub}`" in body, f"cheatsheet missing {sub}"


# ---------------------------------------------------------------------------
# Error cookbook coverage
# ---------------------------------------------------------------------------


def test_error_cookbook_covers_every_declared_error_type() -> None:
    proc = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "check_error_cookbook.py")],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_error_cookbook_uses_alloy_cli_error_anchors() -> None:
    body = _COOKBOOK.read_text(encoding="utf-8")
    # Spot-check a few well-known anchors land as `## name` headers.
    for header in (
        "## DeviceNotFoundError",
        "## PinInvalidError",
        "## ToolchainMissingError",
        "## unknown-clock-profile",
    ):
        assert re.search(rf"(?m)^{re.escape(header)}\b", body)
