"""End-to-end tests for ``alloy setup`` (Wave 3 group 4).

Pinned scenarios (lifted from ``cli-surface/spec.md``):

- setup outside a project + ``--board nucleo_g071rb --auto`` →
  scaffolds + populates ``.alloy/toolchain.lock``.
- setup inside a project + ``--auto`` → no scaffolding overwrite,
  install runs against the resolved family.
- ``--auto`` + closed STDIN → no prompts.
- ``--no-tui`` falls back to the line prompt (Wave-3: line-based is
  the only path; the flag is asserted to be a no-op).
- ``--board`` + ``--family`` mutually exclusive.
- SIGINT mid-install → exit 130 (covered via the
  ``OnboardingCancelledError`` handler in the command body).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import boards as _boards
from alloy_cli.core import toolchain_orchestrator as _orch
from alloy_cli.core.project import (
    SCHEMA_VERSION,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.core.toolchain_orchestrator import InstallOutcome, InstallReport
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def board_catalog(tmp_path, monkeypatch):
    catalog = tmp_path / "boards"
    catalog.mkdir()
    nucleo = catalog / "nucleo_g071rb"
    nucleo.mkdir()
    (nucleo / "board.json").write_text(
        json.dumps(
            {
                "board_id": "nucleo_g071rb",
                "vendor": "st",
                "family": "stm32g0",
                "device": "stm32g071rb",
                "arch": "cortex-m0plus",
                "mcu": "STM32G071RBT6",
                "flash_size_bytes": 131072,
                "summary": "ST Nucleo-G071RB",
                "uart": {"debug": {"peripheral": "USART2", "tx": "PA2", "rx": "PA3"}},
                "leds": [{"name": "ld4", "pin": "PA5"}],
                "clock_profiles": ["default_pll_64mhz"],
                "tier": 1,
            }
        )
    )
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(catalog))
    _boards.load_catalog.cache_clear()
    yield catalog
    _boards.load_catalog.cache_clear()


def _stub_install_family(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace ``install_family`` with a recorder; return captured state."""
    captured: dict = {"calls": []}

    def _fake(manifest, *, project_root=None, on_event=None, **kwargs):
        captured["calls"].append(
            {
                "family_id": manifest.family_id,
                "project_root": project_root,
                "tools_required": tuple(t.tool for t in manifest.required),
            }
        )
        outcomes = tuple(
            InstallOutcome(
                tool=tool.tool,
                version=tool.version,
                state="installed",
                sha256="deadbeef" * 8,
                bytes_downloaded=1024,
            )
            for tool in manifest.required
        )
        return InstallReport(
            family_id=manifest.family_id,
            host=replace(_orch._ts.host_triple()),
            outcomes=outcomes,
            total_bytes_downloaded=sum(o.bytes_downloaded for o in outcomes),
            lockfile_updated=bool(outcomes) and project_root is not None,
            lockfile_path=(project_root / ".alloy" / "toolchain.lock") if project_root else None,
        )

    monkeypatch.setattr(_orch, "install_family", _fake)
    return captured


def _seed_chip_project(project_root: Path, *, family: str = "stm32g0") -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name="fixture"),
        board=None,
        chip=ChipRef(vendor="st", family=family, device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(project_root / "alloy.toml", config)


# ---------------------------------------------------------------------------
# Help + arg parsing
# ---------------------------------------------------------------------------


def test_setup_help_lists_options() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["setup", "--help"])
    assert result.exit_code == 0
    for flag in ("--board", "--family", "--auto", "--no-tui", "--project-dir"):
        assert flag in result.output


def test_setup_board_and_family_are_mutually_exclusive(tmp_path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "setup",
                "--board",
                "nucleo_g071rb",
                "--family",
                "stm32g0",
                "--auto",
            ],
        )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_setup_outside_project_without_overrides_in_non_tty_fails(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """No alloy.toml + no --board / --family + no TTY → must error
    out clean rather than blocking on a prompt the runner can't fulfil."""
    _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["setup", "--auto"])
    assert result.exit_code != 0
    assert "--board" in result.output or "--family" in result.output


# ---------------------------------------------------------------------------
# Outside-a-project: scaffold + install
# ---------------------------------------------------------------------------


def test_setup_outside_project_scaffolds_then_installs(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """Spec scenario: ``setup --board nucleo_g071rb --auto`` in an empty
    directory scaffolds the project AND dispatches the install."""
    captured = _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            [
                "setup",
                "--board",
                "nucleo_g071rb",
                "--auto",
                "--project-dir",
                cwd,
            ],
        )
    assert result.exit_code == 0, result.output
    # Scaffold landed.
    project = Path(cwd)
    assert (project / "alloy.toml").exists()
    assert (project / "CMakeLists.txt").exists()
    # Orchestrator was called once for the resolved family.
    assert len(captured["calls"]) == 1
    assert captured["calls"][0]["family_id"] == "stm32g0"
    assert captured["calls"][0]["project_root"] == project
    # Next-step panel rendered.
    assert "alloy build" in result.output
    assert "alloy flash" in result.output


def test_setup_outside_project_with_family_only_picks_first_board(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """``setup --family stm32g0 --auto`` outside a project picks the
    first board for the family (tier-1 ordering) and scaffolds it."""
    captured = _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            [
                "setup",
                "--family",
                "stm32g0",
                "--auto",
                "--project-dir",
                cwd,
            ],
        )
    assert result.exit_code == 0, result.output
    assert (Path(cwd) / "alloy.toml").exists()
    assert captured["calls"][0]["family_id"] == "stm32g0"


# ---------------------------------------------------------------------------
# Inside-a-project: install only
# ---------------------------------------------------------------------------


def test_setup_inside_project_skips_scaffolding(tmp_path, board_catalog, monkeypatch) -> None:
    """Spec scenario: ``setup --auto`` inside a project resolves the
    family and installs without overwriting any project file."""
    captured = _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        project = Path(cwd)
        _seed_chip_project(project, family="stm32g0")
        # Capture the original alloy.toml mtime so we can assert the
        # scaffolder did not overwrite it.
        original_size = (project / "alloy.toml").stat().st_size
        result = runner.invoke(cli, ["setup", "--auto", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert (project / "alloy.toml").stat().st_size == original_size, (
        "scaffolder must not rewrite the existing alloy.toml"
    )
    assert captured["calls"][0]["family_id"] == "stm32g0"
    assert captured["calls"][0]["project_root"] == project
    # The setup panel mentions the resolved family.
    assert "stm32g0" in result.output


def test_setup_inside_project_with_unknown_family_errors_clean(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """An alloy.toml pinning a family alloy-cli doesn't ship a
    manifest for surfaces a clean error rather than a stack trace."""
    _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        project = Path(cwd)
        _seed_chip_project(project, family="stm32xyz-not-shipped")
        result = runner.invoke(cli, ["setup", "--auto", "--project-dir", cwd])
    assert result.exit_code != 0
    assert "stm32xyz-not-shipped" in result.output or "family" in result.output.lower()


# ---------------------------------------------------------------------------
# --auto suppresses prompts (CI shape)
# ---------------------------------------------------------------------------


def test_setup_auto_inside_project_does_not_prompt(tmp_path, board_catalog, monkeypatch) -> None:
    """``--auto`` must suppress every confirmation; ``Install now?`` must
    NOT appear in the output."""
    _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        project = Path(cwd)
        _seed_chip_project(project, family="stm32g0")
        result = runner.invoke(cli, ["setup", "--auto", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert "Install now?" not in result.output


def test_setup_no_tui_is_accepted_as_a_flag(tmp_path, board_catalog, monkeypatch) -> None:
    """``--no-tui`` parses cleanly today (Wave 3: same line-based path).
    Group 5 will branch on it to gate the Textual hand-off; this test
    pins the forward-compatible no-op."""
    _stub_install_family(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        project = Path(cwd)
        _seed_chip_project(project, family="stm32g0")
        result = runner.invoke(cli, ["setup", "--auto", "--no-tui", "--project-dir", cwd])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Cancellation contract
# ---------------------------------------------------------------------------


def test_setup_install_cancellation_exits_130(tmp_path, board_catalog, monkeypatch) -> None:
    """Mid-install ``OnboardingCancelledError`` → exit code 130."""
    from alloy_cli.core.errors import OnboardingCancelledError

    def _raises(manifest, *, project_root=None, on_event=None, **kwargs):
        raise OnboardingCancelledError("user cancelled")

    monkeypatch.setattr(_orch, "install_family", _raises)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        project = Path(cwd)
        _seed_chip_project(project, family="stm32g0")
        result = runner.invoke(cli, ["setup", "--auto", "--project-dir", cwd])
    assert result.exit_code == 130, result.output
    assert "cancel" in result.output.lower()
