"""Tests for ``add-tui-doctor-screen`` (#20).

Phase 4 covers:

- AutoFix registry against ``FakeRunner`` (4.1).
- Pilot-driven ``DoctorScreen`` flow: stub diagnose returns a
  fixable check, pressing ``f`` swaps the row in place (4.2).
- ``alloy doctor --fix`` exit-code regressions for both success
  and failure paths (4.3).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core.diagnose import (
    AUTO_FIXERS,
    AutoFixOutcome,
    CheckResult,
    DiagnosticReport,
    apply_auto_fix,
    get_auto_fix,
)
from alloy_cli.core.process import FakeRunner
from alloy_cli.main import cli
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.doctor import DoctorScreen

# ---------------------------------------------------------------------------
# Phase 4.1 — AutoFix registry unit tests
# ---------------------------------------------------------------------------


def test_auto_fixers_registry_pins_known_keys() -> None:
    # The registry is the public contract every façade reads.
    # Pinning the keys makes regressions surface immediately.
    assert set(AUTO_FIXERS.keys()) == {"alloy-devices-yml", "mcp"}


def test_get_auto_fix_returns_none_when_check_has_no_marker() -> None:
    check = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="missing",
        # auto_fix=None means "no auto-fixer registered".
    )
    assert get_auto_fix(check) is None


def test_get_auto_fix_returns_none_when_name_not_in_registry() -> None:
    check = CheckResult(
        name="cmake",
        ok=False,
        severity="error",
        message="missing",
        auto_fix="brew install cmake",  # advisory string, no fixer entry
    )
    assert get_auto_fix(check) is None


def test_get_auto_fix_returns_callable_when_registered() -> None:
    check = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="missing",
        auto_fix="git submodule update --init",
    )
    fixer = get_auto_fix(check)
    assert fixer is AUTO_FIXERS["alloy-devices-yml"]


def test_apply_auto_fix_runs_git_submodule_init(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.expect(
        ["git", "submodule", "update", "--init"],
        returncode=0,
        stdout="Submodule path 'data/devices': checked out",
    )
    check = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="missing",
        auto_fix="git submodule update --init",
    )
    outcome = apply_auto_fix(check, project_root=tmp_path, runner=fake)
    assert outcome.ok is True
    assert "Submodule path" in outcome.log
    # Side effect was a single `git submodule update --init` invocation
    # in the project root.
    assert len(fake.calls) == 1
    assert fake.calls[0].args[:4] == ("git", "submodule", "update", "--init")


def test_apply_auto_fix_failure_propagates_log_tail(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.expect(
        ["git", "submodule", "update", "--init"],
        returncode=1,
        stderr="fatal: not a git repository",
    )
    check = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="missing",
        auto_fix="git submodule update --init",
    )
    outcome = apply_auto_fix(check, project_root=tmp_path, runner=fake)
    assert outcome.ok is False
    assert "not a git repository" in outcome.log


def test_apply_auto_fix_pip_install_mcp(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.expect(
        ["pip", "install", "alloy-cli[mcp]"],
        returncode=0,
        stdout="Successfully installed mcp-0.10",
    )
    check = CheckResult(
        name="mcp",
        ok=False,
        severity="warning",
        message="missing",
        auto_fix="pip install 'alloy-cli[mcp]'",
    )
    outcome = apply_auto_fix(check, project_root=tmp_path, runner=fake)
    assert outcome.ok is True
    assert "Successfully installed" in outcome.log


def test_apply_auto_fix_unknown_check_raises() -> None:
    check = CheckResult(
        name="cmake",
        ok=False,
        severity="error",
        message="missing",
        auto_fix=None,
    )
    with pytest.raises(KeyError):
        apply_auto_fix(check, project_root=Path("."), runner=FakeRunner())


# ---------------------------------------------------------------------------
# Phase 4.2 — pilot-driven DoctorScreen flow
# ---------------------------------------------------------------------------


def _stub_report(*checks: CheckResult) -> DiagnosticReport:
    return DiagnosticReport(checks=tuple(checks))


def _stub_diagnose_factory(report: DiagnosticReport):
    def _stub(*, project_dir: Path | None = None) -> DiagnosticReport:
        del project_dir
        return report

    return _stub


@pytest.mark.asyncio
async def test_doctor_screen_lists_every_check_with_glyph(tmp_path: Path) -> None:
    report = _stub_report(
        CheckResult(name="cmake", ok=True, severity="info", message="cmake 3.28"),
        CheckResult(
            name="alloy-devices-yml",
            ok=False,
            severity="warning",
            message="alloy-devices-yml submodule is not initialised.",
            install_hint="git submodule update --init",
            auto_fix="git submodule update --init",
        ),
    )
    screen = DoctorScreen(
        project_dir=tmp_path,
        runner=FakeRunner(),
        diagnose_run=_stub_diagnose_factory(report),
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import DataTable

        table = screen.query_one("#doctor-table", DataTable)
        # Two rows, six columns (status, name, severity, message, hint, fix).
        assert table.row_count == 2
        assert len(table.columns) == 6


@pytest.mark.asyncio
async def test_doctor_screen_f_runs_auto_fix_and_replaces_row(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.expect(
        ["git", "submodule", "update", "--init"], returncode=0, stdout="Submodule synced."
    )
    failing = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="alloy-devices-yml submodule is not initialised.",
        install_hint="git submodule update --init",
        auto_fix="git submodule update --init",
    )
    report = _stub_report(failing)
    screen = DoctorScreen(
        project_dir=tmp_path,
        runner=fake,
        diagnose_run=_stub_diagnose_factory(report),
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import DataTable

        table = screen.query_one("#doctor-table", DataTable)
        # Move the cursor onto the only row, then trigger f.
        from textual.coordinate import Coordinate

        table.cursor_coordinate = Coordinate(0, 0)
        screen.action_auto_fix()
        await pilot.pause()

        # The row was replaced in place — severity flipped to info.
        replaced = screen._report.checks[0]
        assert replaced.severity == "info"
        assert replaced.ok is True

    # The single command we expected was actually invoked.
    assert len(fake.calls) == 1
    assert fake.calls[0].args[:4] == ("git", "submodule", "update", "--init")


@pytest.mark.asyncio
async def test_doctor_screen_f_on_unfixable_row_notifies_only(tmp_path: Path) -> None:
    fake = FakeRunner()
    unfixable = CheckResult(
        name="cmake",
        ok=False,
        severity="error",
        message="cmake is not on PATH.",
        install_hint="brew install cmake",
        # auto_fix=None — no registered fixer
    )
    report = _stub_report(unfixable)
    screen = DoctorScreen(
        project_dir=tmp_path,
        runner=fake,
        diagnose_run=_stub_diagnose_factory(report),
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        screen.action_auto_fix()
        await pilot.pause()

        # Row is unchanged; no subprocess was invoked.
        assert screen._report.checks[0] is unfixable
        assert fake.calls == []


@pytest.mark.asyncio
async def test_doctor_screen_r_reruns_diagnose(tmp_path: Path) -> None:
    reports = iter(
        [
            _stub_report(CheckResult(name="cmake", ok=False, severity="error", message="missing")),
            _stub_report(CheckResult(name="cmake", ok=True, severity="info", message="cmake 3.28")),
        ]
    )

    def _seq(*, project_dir: Path | None = None) -> DiagnosticReport:
        del project_dir
        return next(reports)

    screen = DoctorScreen(project_dir=tmp_path, runner=FakeRunner(), diagnose_run=_seq)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        assert screen._report.checks[0].ok is False
        screen.action_rerun()
        await pilot.pause()
        assert screen._report.checks[0].ok is True


# ---------------------------------------------------------------------------
# Phase 4.3 — alloy doctor --fix exit-code regressions
# ---------------------------------------------------------------------------


def test_doctor_fix_help_lists_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--fix" in result.output


def test_doctor_fix_runs_every_available_fixer(tmp_path: Path, monkeypatch) -> None:
    """--fix iterates over every available auto-fix exactly once."""
    invoked: list[str] = []

    def _fake_fixer(check: CheckResult, runner, project_root: Path) -> AutoFixOutcome:
        del runner, project_root
        invoked.append(check.name)
        return AutoFixOutcome(ok=True, log="ok")

    monkeypatch.setattr(
        _diagnose,
        "AUTO_FIXERS",
        {"alloy-devices-yml": _fake_fixer, "mcp": _fake_fixer},
    )

    fixable = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="missing",
        auto_fix="git submodule update --init",
    )
    fixed = CheckResult(
        name="alloy-devices-yml",
        ok=True,
        severity="info",
        message="present",
    )
    reports = iter([_stub_report(fixable), _stub_report(fixed)])

    def _seq(*, project_dir: Path | None = None) -> DiagnosticReport:
        del project_dir
        return next(reports)

    monkeypatch.setattr(_diagnose, "run", _seq)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["doctor", "--fix", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "alloy-devices-yml" in invoked
    assert "alloy-devices-yml" in result.output


def test_doctor_fix_exits_one_when_a_fixer_fails(tmp_path: Path, monkeypatch) -> None:
    """A failing fixer flips the exit code to 1 even if the second
    diagnose pass shows no error-severity rows."""

    def _failing_fixer(
        check: CheckResult, runner, project_root: Path
    ) -> AutoFixOutcome:
        del check, runner, project_root
        return AutoFixOutcome(ok=False, log="fatal: not a git repository")

    monkeypatch.setattr(
        _diagnose,
        "AUTO_FIXERS",
        {"alloy-devices-yml": _failing_fixer},
    )

    fixable = CheckResult(
        name="alloy-devices-yml",
        ok=False,
        severity="warning",
        message="missing",
        auto_fix="git submodule update --init",
    )
    # Both reports show the same warning row — the fixer failed
    # so the underlying state is unchanged.
    reports = iter([_stub_report(fixable), _stub_report(fixable)])

    def _seq(*, project_dir: Path | None = None) -> DiagnosticReport:
        del project_dir
        return next(reports)

    monkeypatch.setattr(_diagnose, "run", _seq)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["doctor", "--fix", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 1, result.output
    assert "not a git repository" in result.output


def test_doctor_fix_emits_json_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(_diagnose, "AUTO_FIXERS", {})

    def _stub(*, project_dir: Path | None = None) -> DiagnosticReport:
        del project_dir
        return _stub_report(
            CheckResult(name="cmake", ok=True, severity="info", message="cmake 3.28")
        )

    monkeypatch.setattr(_diagnose, "run", _stub)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["doctor", "--fix", "--json", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["auto_fixes"] == []
