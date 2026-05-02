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


# ---------------------------------------------------------------------------
# Codegen integration
# ---------------------------------------------------------------------------


def test_run_skips_codegen_when_alloy_codegen_missing(tmp_path, monkeypatch) -> None:
    """No codegen entry → BuildResult.codegen_returncode is None."""
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: None)

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)

    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
    )
    assert result.ok
    assert result.codegen_returncode is None
    assert result.codegen_skipped is True


def test_run_invokes_codegen_when_entry_is_present(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    from alloy_cli.core.codegen import CodegenEntry

    calls: list[Path] = []

    def _generate(_config, out_dir: Path) -> None:
        calls.append(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "device.hpp").write_text("// generated\n", encoding="utf-8")

    entry = CodegenEntry(version="0.4.2", callable=_generate)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: entry)

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)

    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
    )
    assert result.ok
    assert result.codegen_returncode == 0
    assert result.codegen_skipped is False
    assert len(calls) == 1


def test_run_second_call_skips_codegen_via_stamp(tmp_path, monkeypatch) -> None:
    """Stamp-cache hit on the second build → codegen_skipped=True."""
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    from alloy_cli.core.codegen import CodegenEntry

    calls: list[Path] = []

    def _generate(_config, out_dir: Path) -> None:
        calls.append(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "device.hpp").write_text("// generated\n", encoding="utf-8")

    entry = CodegenEntry(version="0.4.2", callable=_generate)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: entry)

    def _seed_runner() -> FakeRunner:
        runner = FakeRunner()
        runner.expect(["cmake", "-S"], returncode=0)
        runner.expect(["cmake", "--build"], returncode=0)
        return runner

    first = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=_seed_runner(),
    )
    assert first.codegen_skipped is False
    assert len(calls) == 1

    second = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=_seed_runner(),
    )
    assert second.ok
    assert second.codegen_skipped is True
    assert second.codegen_returncode == 0
    assert len(calls) == 1  # codegen NOT re-invoked


def test_run_regen_forces_codegen(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    from alloy_cli.core.codegen import CodegenEntry

    calls: list[Path] = []

    def _generate(_config, out_dir: Path) -> None:
        calls.append(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "device.hpp").write_text("// generated\n", encoding="utf-8")

    entry = CodegenEntry(version="0.4.2", callable=_generate)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: entry)

    def _seed_runner() -> FakeRunner:
        runner = FakeRunner()
        runner.expect(["cmake", "-S"], returncode=0)
        runner.expect(["cmake", "--build"], returncode=0)
        return runner

    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=_seed_runner(),
    )
    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=_seed_runner(),
        regen=True,
    )
    assert len(calls) == 2  # second call forced regen


def test_run_skip_codegen_bypasses_step(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)

    def _fail_generate(_config, _out_dir: Path) -> None:  # pragma: no cover
        raise AssertionError("codegen must NOT run when skip_codegen=True")

    from alloy_cli.core.codegen import CodegenEntry

    entry = CodegenEntry(version="0.4.2", callable=_fail_generate)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: entry)

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)

    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
        skip_codegen=True,
    )
    assert result.ok
    assert result.codegen_returncode is None
    assert result.codegen_skipped is True


def test_run_codegen_failure_aborts_build(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    from alloy_cli.core.codegen import CodegenEntry

    def _bad_generate(_config, _out_dir: Path) -> None:
        raise RuntimeError("codegen exploded")

    entry = CodegenEntry(version="0.4.2", callable=_bad_generate)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: entry)

    fake = FakeRunner()  # cmake should NOT be invoked
    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
    )
    assert not result.ok
    assert result.codegen_returncode == 1
    assert "codegen exploded" in result.codegen_reason
    assert fake.calls == []  # cmake never ran


# ---------------------------------------------------------------------------
# Wave 2: CMake toolchain file generation
# ---------------------------------------------------------------------------


def _seed_lockfile_with_arm_gcc(
    project_root: Path,
    *,
    sha256: str,
    version: str = "14.2.1-1.1",
) -> Path:
    """Write a minimal `.alloy/toolchain.lock` pinning arm-none-eabi-gcc."""
    from alloy_cli.core import lockfile_toolchain as _lf

    lock = _lf.add(_lf.empty(), "arm-none-eabi-gcc", version, sha256)
    lock_path = project_root / ".alloy" / _lf.LOCKFILE_NAME
    _lf.write(lock_path, lock)
    return lock_path


def _seed_store_with_arm_gcc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = "14.2.1-1.1",
) -> str:
    """Install a fake `arm-none-eabi-gcc` (with the matching bundle of
    binaries CMake will look for) into an isolated store; returns the
    pinned sha256 the toolchain.lock should declare.
    """
    import hashlib
    import tarfile

    from alloy_cli.core import toolchain_manager as _tm
    from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact

    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_store" / "tools"))

    # Build a tarball that contains a complete arm-none-eabi-* bin set.
    src = tmp_path / "_pkg" / f"xpack-arm-none-eabi-gcc-{version}" / "bin"
    src.mkdir(parents=True, exist_ok=True)
    binaries = (
        "arm-none-eabi-gcc",
        "arm-none-eabi-g++",
        "arm-none-eabi-gdb",
        "arm-none-eabi-size",
        "arm-none-eabi-objcopy",
        "arm-none-eabi-objdump",
        "arm-none-eabi-ar",
        "arm-none-eabi-ranlib",
    )
    for binary in binaries:
        (src / binary).write_text("#!/bin/sh\nfake\n", encoding="utf-8")

    archive = tmp_path / "arm-gcc.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(
            tmp_path / "_pkg" / f"xpack-arm-none-eabi-gcc-{version}",
            arcname=f"xpack-arm-none-eabi-gcc-{version}",
        )
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()

    artefact = SourceArtifact(
        tool="arm-none-eabi-gcc",
        version=version,
        source="xpack",
        url=f"https://example.com/arm-gcc-{version}.tar.gz",
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir=f"xpack-arm-none-eabi-gcc-{version}",
        binaries=tuple(f"bin/{name}" for name in binaries),
    )

    fake_dl = FakeDownloader()
    fake_dl.expect(artefact.url, archive)
    _tm.install(artefact, downloader=fake_dl)
    return sha


def test_build_with_lockfile_generates_toolchain_cmake_and_passes_arg(
    tmp_path, monkeypatch
) -> None:
    """Project with `.alloy/toolchain.lock` writes
    `.alloy/cache/toolchain.cmake` and passes `-DCMAKE_TOOLCHAIN_FILE=`
    to cmake configure.
    """
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    _make_project(tmp_path)

    sha = _seed_store_with_arm_gcc(tmp_path, monkeypatch)
    _seed_lockfile_with_arm_gcc(tmp_path, sha256=sha)

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)
    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
        skip_codegen=True,
    )
    assert result.ok, result

    # toolchain.cmake exists with absolute paths under the store
    toolchain_cmake = tmp_path / ".alloy" / "cache" / "toolchain.cmake"
    assert toolchain_cmake.exists(), "toolchain.cmake was not generated"
    text = toolchain_cmake.read_text(encoding="utf-8")
    assert "CMAKE_C_COMPILER" in text
    assert "arm-none-eabi-gcc" in text
    assert "/store/" in text  # absolute path under the content-addressed store
    # Stamp file written
    stamp = tmp_path / ".alloy" / "cache" / "toolchain.cmake.stamp"
    assert stamp.exists()

    # cmake configure invocation carried -DCMAKE_TOOLCHAIN_FILE=
    configure_call = next(c for c in fake.calls if c.args[0] == "cmake" and c.args[1] == "-S")
    flags = " ".join(configure_call.args)
    assert "-DCMAKE_TOOLCHAIN_FILE=" in flags
    assert str(toolchain_cmake) in flags


def test_build_without_lockfile_does_not_generate_toolchain_cmake(
    tmp_path, monkeypatch
) -> None:
    """Regression guard: legacy projects (no toolchain.lock) keep the
    pre-Wave-2 cmake invocation byte-identical.
    """
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    _make_project(tmp_path)
    # Critically: NO `.alloy/toolchain.lock` is written.

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)
    result = _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake,
        skip_codegen=True,
    )
    assert result.ok

    # No toolchain.cmake / stamp written
    toolchain_cmake = tmp_path / ".alloy" / "cache" / "toolchain.cmake"
    stamp = tmp_path / ".alloy" / "cache" / "toolchain.cmake.stamp"
    assert not toolchain_cmake.exists()
    assert not stamp.exists()

    # cmake configure invocation does NOT carry -DCMAKE_TOOLCHAIN_FILE
    configure_call = next(c for c in fake.calls if c.args[0] == "cmake" and c.args[1] == "-S")
    for arg in configure_call.args:
        assert not arg.startswith("-DCMAKE_TOOLCHAIN_FILE="), (
            "legacy build leaked a CMAKE_TOOLCHAIN_FILE flag"
        )


def test_build_skips_toolchain_regen_when_stamp_matches(
    tmp_path, monkeypatch
) -> None:
    """A repeat build on an unchanged lockfile must NOT rewrite the
    toolchain.cmake file (the stamp short-circuits regeneration).
    """
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    _make_project(tmp_path)
    sha = _seed_store_with_arm_gcc(tmp_path, monkeypatch)
    _seed_lockfile_with_arm_gcc(tmp_path, sha256=sha)

    # First build — generates toolchain.cmake.
    fake1 = FakeRunner()
    fake1.expect(["cmake", "-S"], returncode=0)
    fake1.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake1,
        skip_codegen=True,
    )

    cmake_path = tmp_path / ".alloy" / "cache" / "toolchain.cmake"
    first_mtime = cmake_path.stat().st_mtime_ns

    # Second build — stamp matches, file should NOT be touched.
    import time as _time

    _time.sleep(0.01)  # ensure mtime resolution would catch a rewrite
    fake2 = FakeRunner()
    fake2.expect(["cmake", "-S"], returncode=0)
    fake2.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake2,
        skip_codegen=True,
    )
    second_mtime = cmake_path.stat().st_mtime_ns
    assert second_mtime == first_mtime, (
        "stamp short-circuit didn't kick in — toolchain.cmake was rewritten"
    )


def test_build_with_lockfile_pinning_missing_version_raises_typed(
    tmp_path, monkeypatch
) -> None:
    """When the lockfile pins (tool, version, sha) but the local store
    has no matching extraction, build aborts with the typed
    `family-toolchain-installer-version-mismatch` error.
    """
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_empty_store" / "tools"))
    _make_project(tmp_path)
    _seed_lockfile_with_arm_gcc(tmp_path, sha256="0" * 64, version="14.2.1-1.1")

    fake = FakeRunner()  # cmake must NOT be invoked
    with pytest.raises(AlloyCliError, match=r"version-mismatch|toolchain\.lock"):
        _build.run(
            project_root=tmp_path,
            profile="debug",
            require_toolchain=False,
            runner=fake,
            skip_codegen=True,
        )
    # cmake never ran (we aborted before configure)
    assert fake.calls == []


def test_build_lockfile_change_invalidates_toolchain_stamp(
    tmp_path, monkeypatch
) -> None:
    """Editing toolchain.lock between two builds must force the
    toolchain.cmake to be rewritten (different stamp).
    """
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)
    _make_project(tmp_path)

    sha_v1 = _seed_store_with_arm_gcc(tmp_path, monkeypatch, version="14.2.1-1.1")
    _seed_lockfile_with_arm_gcc(tmp_path, sha256=sha_v1, version="14.2.1-1.1")

    fake1 = FakeRunner()
    fake1.expect(["cmake", "-S"], returncode=0)
    fake1.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake1,
        skip_codegen=True,
    )
    cmake_path = tmp_path / ".alloy" / "cache" / "toolchain.cmake"
    first_text = cmake_path.read_text(encoding="utf-8")

    # Install a second version + repin the lockfile
    sha_v2 = _seed_store_with_arm_gcc(tmp_path, monkeypatch, version="14.3.0")
    _seed_lockfile_with_arm_gcc(tmp_path, sha256=sha_v2, version="14.3.0")

    fake2 = FakeRunner()
    fake2.expect(["cmake", "-S"], returncode=0)
    fake2.expect(["cmake", "--build"], returncode=0)
    _build.run(
        project_root=tmp_path,
        profile="debug",
        require_toolchain=False,
        runner=fake2,
        skip_codegen=True,
    )
    second_text = cmake_path.read_text(encoding="utf-8")
    assert second_text != first_text
    # The new toolchain file references the v14.3.0 store path
    assert "14.3.0" in second_text
