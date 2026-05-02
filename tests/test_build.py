"""Tests for ``alloy_cli.core.build``: cmake + ninja orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core import build as _build
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    BoardRef,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)

# ---------------------------------------------------------------------------
# Fixture project
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, *, with_board: bool = True) -> Path:
    if with_board:
        config = ProjectConfig(
            schema_version="1.0.0",
            project=ProjectMeta(name="firmware"),
            board=BoardRef(id="nucleo_g071rb"),
            chip=None,
            clocks={},
            peripherals=(),
            build={"profile": "debug"},
            flash={},
            raw={},
        )
    else:
        config = ProjectConfig(
            schema_version="1.0.0",
            project=ProjectMeta(name="firmware"),
            board=None,
            chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
            clocks={},
            peripherals=(),
            build={"profile": "debug"},
            flash={},
            raw={},
        )
    write(tmp_path / PROJECT_FILE, config)
    return tmp_path


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_run_rejects_unknown_profile(tmp_path) -> None:
    _make_project(tmp_path)
    with pytest.raises(AlloyCliError, match="profile"):
        _build.run(
            project_root=tmp_path,
            profile="yolo",  # type: ignore[arg-type]
            require_toolchain=False,
            runner=FakeRunner(),
        )


def test_run_returns_failure_when_cmake_configure_fails(tmp_path) -> None:
    _make_project(tmp_path)
    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=2, stdout="some error")
    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
    )
    assert not result.ok
    assert result.cmake_returncode == 2
    assert result.build_returncode == -1
    assert result.elf_path is None


def test_run_invokes_cmake_then_build_and_finds_elf(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    # Pretend `size` isn't on PATH so parse_elf returns None instead of
    # invoking the runner with an unexpected command.
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)

    # Pre-create an ELF inside the build dir so _resolve_elf finds it.
    build_dir = tmp_path / ".alloy" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / "firmware.elf"
    elf.write_bytes(b"\x7fELF\x01\x01\x01")

    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
    )
    assert result.ok
    assert result.elf_path == elf
    # cmake configure + build — exactly two calls observed
    assert [c.args[:2] for c in fake.calls[:2]] == [("cmake", "-S"), ("cmake", "--build")]


def test_run_clean_wipes_build_dir(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    build_dir = tmp_path / ".alloy" / "build"
    build_dir.mkdir(parents=True)
    (build_dir / "stale.txt").write_text("old")

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="debug",
        clean=True,
        require_toolchain=False,
        runner=fake,
    )
    # The stale file is gone — cmake just got a fresh dir.
    assert not (build_dir / "stale.txt").exists()


def test_run_release_profile_passes_release_to_cmake(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="release",
        require_toolchain=False,
        runner=fake,
    )
    cfg = fake.calls[0]
    assert "-DCMAKE_BUILD_TYPE=Release" in cfg.args


def test_run_chip_only_project_still_invokes_cmake(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, with_board=False)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
    )
    # Both stages dispatched.
    assert len(fake.calls) >= 2
