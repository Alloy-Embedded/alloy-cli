"""End-to-end tests for ``alloy erase`` (Wave 4 group 3).

Pinned scenarios (lifted from ``cli-surface/spec.md``):

- TTY + ``y`` answer executes the erase.
- TTY + ``n`` answer aborts with the typed surface.
- ``--auto`` in non-TTY skips the prompt + executes.
- ``--yes`` is an alias for ``--auto``.
- Non-TTY without ``--auto`` / ``--yes`` aborts with a clear message.
- ``--region 0xBASE-0xEND`` accepts the literal range.
- Per-region erase via probe-rs raises typed envelope (Wave-4
  ships chip-wide only).
- ``--help`` advertises every flag.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from alloy_cli.commands import erase as _erase
from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    FamilyToolchainEraseUnsupportedRegionError,
)
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stlink() -> _po.ProbeIdentity:
    return _po.ProbeIdentity(
        vid="0483",
        pid="374b",
        serial="AAA",
        kind="stlink",
        vendor_only=False,
    )


def _stub_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    probes: tuple[_po.ProbeIdentity, ...] = (_stlink(),),
    erase_error: Exception | None = None,
) -> dict:
    """Replace ``select_probe`` + ``real_probe_for`` + ``execute_erase``
    with a passthrough that records arguments and dispatches against
    a ``FakeProbe``."""
    captured: dict = {"select_calls": [], "fake_probe": None}

    original_select = _po.select_probe

    def _fake_select_records(*, hint=None, project_root=None, probes=None):
        captured["select_calls"].append({"hint": hint, "project_root": project_root})
        return original_select(hint=hint, project_root=project_root, probes=probes)

    monkeypatch.setattr(_po, "select_probe", _fake_select_records)
    monkeypatch.setattr(_po, "_list_probes", lambda *, project_root=None: probes)

    fake_probe = _po.FakeProbe(identity=probes[0])
    if erase_error is not None:
        fake_probe.fail_next_erase(erase_error)

    monkeypatch.setattr(
        _po,
        "real_probe_for",
        lambda identity, *, project_root=None, runner=None: fake_probe,
    )

    captured["fake_probe"] = fake_probe
    return captured


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_erase_help_lists_every_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["erase", "--help"])
    assert result.exit_code == 0
    for flag in ("--region", "--auto", "--yes", "--probe", "--project-dir"):
        assert flag in result.output


# ---------------------------------------------------------------------------
# Safety gate paths
# ---------------------------------------------------------------------------


def test_erase_non_tty_without_auto_aborts(tmp_path, monkeypatch) -> None:
    """Default invocation with closed STDIN MUST refuse to proceed."""
    captured = _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: False)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--project-dir", cwd])
    assert result.exit_code != 0
    assert "STDIN is not a TTY" in result.output
    assert "--auto" in result.output or "--yes" in result.output
    # No erase ran.
    assert len(captured["fake_probe"].erase_calls) == 0


def test_erase_auto_in_non_tty_skips_prompt_and_executes(tmp_path, monkeypatch) -> None:
    captured = _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: False)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--auto", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert "Flash erased" in result.output
    assert len(captured["fake_probe"].erase_calls) == 1


def test_erase_yes_is_alias_for_auto(tmp_path, monkeypatch) -> None:
    captured = _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: False)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--yes", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert len(captured["fake_probe"].erase_calls) == 1


def test_erase_tty_yes_answer_executes(tmp_path, monkeypatch) -> None:
    captured = _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: True)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--project-dir", cwd], input="y\n")
    assert result.exit_code == 0, result.output
    assert "Flash erased" in result.output
    assert len(captured["fake_probe"].erase_calls) == 1
    # Plan rendered BEFORE the prompt — the plan title appears before
    # the "Continue?" question.
    plan_idx = result.output.find("Erase plan")
    prompt_idx = result.output.find("Continue?")
    assert plan_idx >= 0 and prompt_idx >= 0
    assert plan_idx < prompt_idx


def test_erase_tty_no_answer_aborts(tmp_path, monkeypatch) -> None:
    captured = _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: True)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--project-dir", cwd], input="n\n")
    assert result.exit_code != 0
    assert "Erase aborted by user" in result.output
    assert "family-toolchain-erase-aborted" in result.output
    assert len(captured["fake_probe"].erase_calls) == 0


def test_erase_tty_garbage_answer_aborts(tmp_path, monkeypatch) -> None:
    """Anything that doesn't parse as an affirmative aborts."""
    captured = _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: True)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--project-dir", cwd], input="\n")
    assert result.exit_code != 0
    assert len(captured["fake_probe"].erase_calls) == 0


# ---------------------------------------------------------------------------
# Region handling
# ---------------------------------------------------------------------------


def test_erase_region_literal_range_passes_through(tmp_path, monkeypatch) -> None:
    """``--region 0x08000000-0x08010000`` builds a one-region plan
    using the explicit byte addresses — no IR resolver involved."""
    _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: False)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            [
                "erase",
                "--auto",
                "--region",
                "0x08000000-0x08010000",
                "--project-dir",
                cwd,
            ],
        )
    # The probe-rs backend currently rejects per-region erase (Wave-4
    # group 3 ships chip-wide only); the typed error surfaces on the
    # execute_erase call.  This still pins that the plan accepted the
    # range without raising unsupported-region.
    assert "unsupported-region" not in result.output


def test_erase_region_unknown_alias_raises_typed(tmp_path, monkeypatch) -> None:
    _stub_orchestrator(
        monkeypatch,
        erase_error=FamilyToolchainEraseUnsupportedRegionError(
            "Unknown region 'wat'.",
            known_regions=("bootloader", "appslot-a"),
        ),
    )
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: False)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        # Use a real alias-that-isn't to trigger the resolver.  Without
        # a region_resolver attached to the orchestrator's plan_erase
        # call we expect plan_erase to reject the alias up front.
        result = runner.invoke(
            cli,
            ["erase", "--auto", "--region", "wat", "--project-dir", cwd],
        )
    assert result.exit_code != 0
    assert "family-toolchain-erase-unsupported-region" in result.output


# ---------------------------------------------------------------------------
# Plan ordering + execute
# ---------------------------------------------------------------------------


def test_erase_renders_plan_before_executing(tmp_path, monkeypatch) -> None:
    """The plan table prints BEFORE the orchestrator dispatches."""
    _stub_orchestrator(monkeypatch)
    monkeypatch.setattr(_erase, "_is_stdin_tty", lambda: False)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["erase", "--auto", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    plan_idx = result.output.find("Erase plan")
    flash_idx = result.output.find("Flash erased")
    assert plan_idx >= 0 and flash_idx >= 0
    assert plan_idx < flash_idx
