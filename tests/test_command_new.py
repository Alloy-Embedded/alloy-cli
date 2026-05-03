"""Smoke tests for the ``alloy new`` Click command surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import boards
from alloy_cli.main import cli


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
    boards.load_catalog.cache_clear()
    yield catalog
    boards.load_catalog.cache_clear()


def test_alloy_new_help_lists_options() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["new", "--help"])
    assert result.exit_code == 0
    assert "--board" in result.output
    assert "--device" in result.output
    assert "--license" in result.output
    assert "--git" in result.output
    assert "--force" in result.output


def test_alloy_new_without_board_or_device_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["new", "firmware"])
    assert result.exit_code != 0
    assert "alloy boards" in result.output or "--board" in result.output


def test_alloy_new_with_both_board_and_device_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "new",
                "firmware",
                "--board",
                "nucleo_g071rb",
                "--device",
                "st/stm32g0/stm32g071rb",
            ],
        )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_alloy_new_with_invalid_device_format_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "firmware", "--device", "stm32g071rb"],
        )
    assert result.exit_code != 0
    assert "VENDOR/FAMILY/DEVICE" in result.output


def test_alloy_new_board_writes_a_buildable_project_tree(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "nucleo_g071rb", "--no-git"],
        )
        assert result.exit_code == 0, result.output
        project = Path(cwd) / "firmware"
        assert (project / "alloy.toml").exists()
        assert (project / "CMakeLists.txt").exists()
        assert (project / "src" / "main.cpp").exists()
        assert (project / "README.md").exists()
        assert (project / ".gitignore").exists()
        assert (project / "LICENSE").exists()


def test_alloy_new_unknown_board_surfaces_clean_error(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "fictional_board", "--no-git"],
        )
    assert result.exit_code != 0
    assert "fictional_board" in result.output


def test_alloy_new_invalid_project_name_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "1bad-name", "--board", "nucleo_g071rb", "--no-git"],
        )
    assert result.exit_code != 0
    assert "Project name" in result.output


# ---------------------------------------------------------------------------
# Wave 3: post-scaffold install prompt
# ---------------------------------------------------------------------------


def test_should_offer_install_explicit_true_wins() -> None:
    from alloy_cli.commands.new import _should_offer_install

    assert _should_offer_install(install_flag=True, tty=False) is True
    assert _should_offer_install(install_flag=True, tty=True) is True


def test_should_offer_install_explicit_false_wins() -> None:
    from alloy_cli.commands.new import _should_offer_install

    assert _should_offer_install(install_flag=False, tty=False) is False
    assert _should_offer_install(install_flag=False, tty=True) is False


def test_should_offer_install_default_follows_tty() -> None:
    from alloy_cli.commands.new import _should_offer_install

    assert _should_offer_install(install_flag=None, tty=True) is True
    assert _should_offer_install(install_flag=None, tty=False) is False


def _fake_install_factory(captured: dict, lockfile_updated: bool = True):
    """Build a stand-in for ``toolchain_orchestrator.install_family``
    that records its arguments and returns a frozen empty report.

    Tests that exercise the CLI plumbing don't want the real download
    pipeline — they want to assert "the orchestrator was called with
    the right family + project_root, and the next-step panel reflects
    the outcome."
    """
    from alloy_cli.core import tool_sources as _ts
    from alloy_cli.core.toolchain_orchestrator import InstallReport

    def _fake(manifest, *, project_root=None, on_event=None, **kwargs):
        captured["called"] = True
        captured["family_id"] = manifest.family_id
        captured["project_root"] = project_root
        captured["kwargs"] = kwargs
        if on_event is not None:
            captured["on_event_was_set"] = True
        return InstallReport(
            family_id=manifest.family_id,
            host=_ts.host_triple(),
            outcomes=(),
            total_bytes_downloaded=0,
            lockfile_updated=lockfile_updated,
            lockfile_path=(project_root / ".alloy" / "toolchain.lock") if project_root and lockfile_updated else None,
        )

    return _fake


def test_alloy_new_install_toolchain_auto_dispatches_orchestrator(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """``--install-toolchain --auto`` runs install_family non-interactively."""
    from alloy_cli.commands import new as _new

    captured: dict = {}
    monkeypatch.setattr(_new._orch, "install_family", _fake_install_factory(captured))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "new",
                "firmware",
                "--board",
                "nucleo_g071rb",
                "--no-git",
                "--install-toolchain",
                "--auto",
            ],
        )
    assert result.exit_code == 0, result.output
    assert captured.get("called") is True
    assert captured["family_id"] == "stm32g0"
    assert captured["project_root"].name == "firmware"
    assert captured.get("on_event_was_set") is True


def test_alloy_new_no_install_toolchain_skips_dispatch(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """``--no-install-toolchain`` never spawns the orchestrator."""
    from alloy_cli.commands import new as _new

    captured: dict = {}
    monkeypatch.setattr(_new._orch, "install_family", _fake_install_factory(captured))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            [
                "new",
                "firmware",
                "--board",
                "nucleo_g071rb",
                "--no-git",
                "--no-install-toolchain",
            ],
        )
    assert result.exit_code == 0, result.output
    assert captured == {}, "orchestrator must not be called when the flag is False"
    # The next-step panel still names the deferred command.
    assert "alloy toolchain install" in result.output
    # No lockfile materialised.
    assert not (Path(cwd) / "firmware" / ".alloy" / "toolchain.lock").exists()


def test_alloy_new_non_tty_default_skips_dispatch(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """In a non-TTY context (CliRunner default), the missing flag means skip."""
    from alloy_cli.commands import new as _new

    captured: dict = {}
    monkeypatch.setattr(_new._orch, "install_family", _fake_install_factory(captured))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "nucleo_g071rb", "--no-git"],
        )
    assert result.exit_code == 0, result.output
    assert captured == {}, "non-TTY default must not dispatch the install"
    assert "alloy toolchain install" in result.output


def test_alloy_new_tty_prompt_yes_dispatches(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """A simulated TTY + 'Y' answer at the prompt dispatches the orchestrator."""
    from alloy_cli.commands import new as _new

    captured: dict = {}
    monkeypatch.setattr(_new._orch, "install_family", _fake_install_factory(captured))
    # Force the TTY branch.  Both the command's `sys.stdin.isatty()`
    # check AND Click's confirm prompt look at this.
    monkeypatch.setattr(_new, "_is_stdin_tty", lambda: True)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "nucleo_g071rb", "--no-git"],
            input="y\n",
        )
    assert result.exit_code == 0, result.output
    assert captured.get("called") is True
    # The plan rendered before the prompt — the table title should appear
    # before the "Install now?" question.
    plan_idx = result.output.find("Install plan")
    prompt_idx = result.output.find("Install now?")
    assert plan_idx >= 0 and prompt_idx >= 0
    assert plan_idx < prompt_idx, (
        "the install plan must render before the confirmation prompt"
    )


def test_alloy_new_tty_prompt_no_skips_dispatch(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """A simulated TTY + 'n' answer skips the dispatch and points at the deferred command."""
    from alloy_cli.commands import new as _new

    captured: dict = {}
    monkeypatch.setattr(_new._orch, "install_family", _fake_install_factory(captured))
    monkeypatch.setattr(_new, "_is_stdin_tty", lambda: True)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "nucleo_g071rb", "--no-git"],
            input="n\n",
        )
    assert result.exit_code == 0, result.output
    assert captured == {}
    assert "alloy toolchain install" in result.output
    assert not (Path(cwd) / "firmware" / ".alloy" / "toolchain.lock").exists()


def test_alloy_new_install_toolchain_auto_emits_summary_panel(
    tmp_path, board_catalog, monkeypatch
) -> None:
    """The post-scaffold next-step panel is always printed, even after install."""
    from alloy_cli.commands import new as _new

    captured: dict = {}
    monkeypatch.setattr(_new._orch, "install_family", _fake_install_factory(captured))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "new",
                "firmware",
                "--board",
                "nucleo_g071rb",
                "--no-git",
                "--install-toolchain",
                "--auto",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "alloy build" in result.output
    assert "alloy flash" in result.output
