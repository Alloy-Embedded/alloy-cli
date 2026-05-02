"""Tests for the wave-2 ``alloy update`` upgraders + atomic apply semantics."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import update as _update
from alloy_cli.core.lockfile import AlloyLockfile, write_lock
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    AlloyDir,
    BoardRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.core.update import (
    DEPENDENCY_ORDER,
    UPGRADERS,
    Upgrade,
    UpgradeContext,
    UpgradeOutcome,
    apply_upgrades,
    git_submodule_upgrader,
    pip_upgrader,
    resolve_upgrades,
)
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_project(root: Path) -> ProjectConfig:
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(
            name="firmware",
            alloy="0.7.5",
            alloy_codegen="0.4.2",
            alloy_devices_yml="1.5.1",
            alloy_cli="0.5.0",
        ),
        board=BoardRef(id="nucleo_g071rb"),
        chip=None,
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(root / PROJECT_FILE, config)
    return config


def _seed_lock(
    root: Path,
    *,
    alloy: str | None = "0.7.3",
    alloy_codegen: str | None = "0.4.1",
    alloy_devices_yml: str | None = "1.5.0",
    alloy_cli: str | None = "0.5.0",
) -> AlloyLockfile:
    layout = AlloyDir(root=root)
    layout.ensure()
    lock = AlloyLockfile(
        schema_version="1.0.0",
        alloy=alloy,
        alloy_codegen=alloy_codegen,
        alloy_devices_yml=alloy_devices_yml,
        alloy_cli=alloy_cli,
    )
    write_lock(layout.lockfile, lock)
    return lock


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_dependency_order_is_correct() -> None:
    assert DEPENDENCY_ORDER == (
        "alloy-devices-yml",
        "alloy-codegen",
        "alloy",
        "alloy-cli",
    )


def test_upgraders_registry_covers_every_component() -> None:
    assert set(UPGRADERS) == set(DEPENDENCY_ORDER)


# ---------------------------------------------------------------------------
# pip_upgrader
# ---------------------------------------------------------------------------


def _ctx(tmp_path: Path, runner: FakeRunner, lock: AlloyLockfile | None = None) -> UpgradeContext:
    return UpgradeContext(
        project_dir=tmp_path,
        runner=runner,
        current_lock=lock
        or AlloyLockfile(
            schema_version="1.0.0",
            alloy=None,
            alloy_codegen=None,
            alloy_devices_yml=None,
            alloy_cli=None,
        ),
    )


def test_pip_upgrader_invokes_pip_install_with_pinned_version(tmp_path) -> None:
    fake = FakeRunner()
    fake.expect(
        [sys.executable, "-m", "pip", "install", "--upgrade", "alloy==0.7.5"],
        returncode=0,
        stdout="Successfully installed alloy-0.7.5",
    )
    upgrade = Upgrade(component="alloy", current="0.7.3", target="0.7.5")
    outcome = pip_upgrader("alloy")(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is True
    assert "Successfully installed" in outcome.log


def test_pip_upgrader_no_op_when_already_at_target(tmp_path) -> None:
    fake = FakeRunner()  # no expected calls
    upgrade = Upgrade(component="alloy", current="0.7.5", target="0.7.5")
    outcome = pip_upgrader("alloy")(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is True
    assert "already at 0.7.5" in outcome.log
    assert fake.calls == []


def test_pip_upgrader_with_restart_marks_restart_required(tmp_path) -> None:
    fake = FakeRunner()
    fake.expect(
        [sys.executable, "-m", "pip", "install", "--upgrade", "alloy-cli==0.6.0"],
        returncode=0,
    )
    upgrade = Upgrade(component="alloy-cli", current="0.5.0", target="0.6.0")
    outcome = pip_upgrader("alloy-cli", restart_required=True)(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is True
    assert outcome.restart_required is True


def test_pip_upgrader_propagates_failure(tmp_path) -> None:
    fake = FakeRunner()
    fake.expect(
        [sys.executable, "-m", "pip", "install", "--upgrade", "alloy==0.7.5"],
        returncode=1,
        stderr="ERROR: package not found",
    )
    upgrade = Upgrade(component="alloy", current="0.7.3", target="0.7.5")
    outcome = pip_upgrader("alloy")(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is False
    assert "ERROR: package not found" in outcome.log


# ---------------------------------------------------------------------------
# git_submodule_upgrader
# ---------------------------------------------------------------------------


def test_submodule_upgrader_runs_fetch_then_checkout(tmp_path) -> None:
    submodule = tmp_path / "data" / "devices"
    submodule.mkdir(parents=True)
    fake = FakeRunner()
    fake.expect(["git", "fetch", "--tags", "origin"], returncode=0)
    fake.expect(["git", "checkout", "v1.5.1"], returncode=0)

    upgrade = Upgrade(component="alloy-devices-yml", current="1.5.0", target="1.5.1")
    outcome = git_submodule_upgrader(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is True
    assert "v1.5.1" in outcome.log


def test_submodule_upgrader_falls_back_to_unprefixed_tag(tmp_path) -> None:
    submodule = tmp_path / "data" / "devices"
    submodule.mkdir(parents=True)
    fake = FakeRunner()
    fake.expect(["git", "fetch", "--tags", "origin"], returncode=0)
    fake.expect(["git", "checkout", "v1.5.1"], returncode=1, stderr="not a ref")
    fake.expect(["git", "checkout", "1.5.1"], returncode=0)

    upgrade = Upgrade(component="alloy-devices-yml", current="1.5.0", target="1.5.1")
    outcome = git_submodule_upgrader(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is True


def test_submodule_upgrader_fails_when_submodule_missing(tmp_path) -> None:
    fake = FakeRunner()
    upgrade = Upgrade(component="alloy-devices-yml", current=None, target="1.5.1")
    outcome = git_submodule_upgrader(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is False
    assert "submodule" in outcome.log
    assert fake.calls == []


def test_submodule_upgrader_fails_when_neither_tag_resolves(tmp_path) -> None:
    submodule = tmp_path / "data" / "devices"
    submodule.mkdir(parents=True)
    fake = FakeRunner()
    fake.expect(["git", "fetch", "--tags", "origin"], returncode=0)
    fake.expect(["git", "checkout", "v9.9.9"], returncode=1, stderr="bad ref")
    fake.expect(["git", "checkout", "9.9.9"], returncode=1, stderr="bad ref")

    upgrade = Upgrade(component="alloy-devices-yml", current="1.5.0", target="9.9.9")
    outcome = git_submodule_upgrader(upgrade, _ctx(tmp_path, fake))
    assert outcome.ok is False
    assert "9.9.9" in outcome.log


# ---------------------------------------------------------------------------
# apply_upgrades — atomic semantics
# ---------------------------------------------------------------------------


def test_apply_upgrades_runs_in_dependency_order(tmp_path) -> None:
    config = _seed_project(tmp_path)
    _seed_lock(tmp_path)
    upgrades = resolve_upgrades(
        config,
        AlloyLockfile(
            schema_version="1.0.0",
            alloy="0.7.3",
            alloy_codegen="0.4.1",
            alloy_devices_yml="1.5.0",
            alloy_cli="0.5.0",
        ),
    )

    invoked: list[str] = []

    def _track(name: str) -> _update.ComponentUpgrader:
        def _impl(upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
            invoked.append(upgrade.component)
            return UpgradeOutcome(ok=True, log=f"{name}-ok")

        return _impl

    upgraders = {name: _track(name) for name in UPGRADERS}
    report = apply_upgrades(
        tmp_path,
        upgrades=upgrades,
        config=config,
        dry_run=False,
        upgraders=upgraders,
        runner=FakeRunner(),
    )
    assert report.aborted is False
    # Only changed components run.  alloy-cli matches lock vs target → skipped.
    assert invoked == ["alloy-devices-yml", "alloy-codegen", "alloy"]


def test_apply_upgrades_aborts_on_failure_and_keeps_lockfile(tmp_path) -> None:
    config = _seed_project(tmp_path)
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    initial = AlloyLockfile(
        schema_version="1.0.0",
        alloy="0.7.3",
        alloy_codegen="0.4.1",
        alloy_devices_yml="1.5.0",
        alloy_cli="0.5.0",
    )
    write_lock(layout.lockfile, initial)
    before = layout.lockfile.read_bytes()

    def _ok(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="ok")

    def _fail(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=False, log="boom")

    upgraders = {
        "alloy-devices-yml": _ok,
        "alloy-codegen": _fail,  # second in dependency order
        "alloy": _ok,
        "alloy-cli": _ok,
    }
    upgrades = resolve_upgrades(config, initial)
    report = apply_upgrades(
        tmp_path,
        upgrades=upgrades,
        config=config,
        dry_run=False,
        upgraders=upgraders,
        runner=FakeRunner(),
    )
    assert report.aborted is True
    assert report.failure_component == "alloy-codegen"
    assert report.new_lock is None
    assert layout.lockfile.read_bytes() == before  # untouched


def test_apply_upgrades_dry_run_returns_outcomes_without_writing(tmp_path) -> None:
    config = _seed_project(tmp_path)
    initial = _seed_lock(tmp_path)
    before = (AlloyDir(root=tmp_path).lockfile).read_bytes()
    upgrades = resolve_upgrades(config, initial)

    def _track(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        raise AssertionError("dry-run must NOT invoke upgraders")

    upgraders = {name: _track for name in UPGRADERS}
    report = apply_upgrades(
        tmp_path,
        upgrades=upgrades,
        config=config,
        dry_run=True,
        upgraders=upgraders,
        runner=FakeRunner(),
    )
    assert report.aborted is False
    assert all(outcome.ok and outcome.log == "dry-run" for _, outcome in report.outcomes)
    assert (AlloyDir(root=tmp_path).lockfile).read_bytes() == before


def test_apply_upgrades_propagates_restart_required(tmp_path) -> None:
    config = _seed_project(tmp_path)
    _seed_lock(tmp_path, alloy_cli="0.4.0")  # → 0.5.0 upgrade

    def _ok(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="ok")

    def _restart(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="upgraded", restart_required=True)

    upgraders = {
        "alloy-devices-yml": _ok,
        "alloy-codegen": _ok,
        "alloy": _ok,
        "alloy-cli": _restart,
    }
    upgrades = resolve_upgrades(
        config,
        AlloyLockfile(
            schema_version="1.0.0",
            alloy="0.7.3",
            alloy_codegen="0.4.1",
            alloy_devices_yml="1.5.0",
            alloy_cli="0.4.0",
        ),
    )
    report = apply_upgrades(
        tmp_path,
        upgrades=upgrades,
        config=config,
        dry_run=False,
        upgraders=upgraders,
        runner=FakeRunner(),
    )
    assert report.aborted is False
    assert report.restart_required is True


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_alloy_update_aborted_run_surfaces_failure_summary(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)
    _seed_lock(tmp_path)

    def _ok(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="ok")

    def _fail(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=False, log="ERROR: pip exploded")

    monkeypatch.setattr(
        _update,
        "UPGRADERS",
        {
            "alloy-devices-yml": _ok,
            "alloy-codegen": _fail,
            "alloy": _ok,
            "alloy-cli": _ok,
        },
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "ERROR: pip exploded" in result.output
    assert "lockfile unchanged" in result.output


def test_alloy_update_success_rewrites_lockfile_with_new_versions(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)
    _seed_lock(tmp_path)

    def _ok(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="ok")

    monkeypatch.setattr(
        _update,
        "UPGRADERS",
        {name: _ok for name in DEPENDENCY_ORDER},
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    layout = AlloyDir(root=tmp_path)
    text = layout.lockfile.read_text(encoding="utf-8")
    assert 'alloy = "0.7.5"' in text
    assert 'alloy-codegen = "0.4.2"' in text


def test_alloy_update_restart_message_when_alloy_cli_upgraded(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)
    _seed_lock(tmp_path, alloy_cli="0.4.0")

    def _ok(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="ok")

    def _restart(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        return UpgradeOutcome(ok=True, log="upgraded", restart_required=True)

    monkeypatch.setattr(
        _update,
        "UPGRADERS",
        {
            "alloy-devices-yml": _ok,
            "alloy-codegen": _ok,
            "alloy": _ok,
            "alloy-cli": _restart,
        },
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Re-launch" in result.output


def test_alloy_update_dry_run_does_not_modify_lockfile_or_invoke_upgraders(
    tmp_path, monkeypatch
) -> None:
    _seed_project(tmp_path)
    _seed_lock(tmp_path)
    layout = AlloyDir(root=tmp_path)
    before = layout.lockfile.read_bytes()

    def _explode(_upgrade: Upgrade, _ctx_: UpgradeContext) -> UpgradeOutcome:
        raise AssertionError("dry-run must NOT call upgraders")

    monkeypatch.setattr(
        _update,
        "UPGRADERS",
        {name: _explode for name in DEPENDENCY_ORDER},
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--dry-run", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0.7.3" in result.output and "0.7.5" in result.output
    assert layout.lockfile.read_bytes() == before


@pytest.mark.parametrize("hint", ["dry-run", "lockfile not modified"])
def test_alloy_update_dry_run_says_so(tmp_path, hint) -> None:
    _seed_project(tmp_path)
    _seed_lock(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--dry-run", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert hint in result.output
