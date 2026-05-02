"""Tests for ``alloy_cli.core.debug`` — gdb-server invocation builder."""

from __future__ import annotations

from pathlib import Path

from alloy_cli.core.debug import build_invocation


def test_build_invocation_includes_chip_and_elf(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        gdb_ui="echo",  # any binary that exists; resolves via shutil.which
        require_toolchain=False,
    )
    assert "stm32g071rb" in session.server_args
    assert str(elf) in session.server_args
    assert any("target extended-remote" in a for a in session.gdb_args)
    assert session.gdb_port == 1337


def test_build_invocation_uses_alloy_gdb_env(monkeypatch, tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"")
    monkeypatch.setenv("ALLOY_GDB", "/usr/bin/gdb-from-env")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        require_toolchain=False,
    )
    assert session.gdb_args[0] == "/usr/bin/gdb-from-env"


def test_build_invocation_custom_port(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        gdb_port=4242,
        require_toolchain=False,
    )
    assert session.gdb_port == 4242
    assert any(":4242" in a for a in session.server_args)
    assert any(":4242" in a for a in session.gdb_args)


def test_build_invocation_uses_explicit_gdb_ui(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        gdb_ui="my-special-gdb",
        require_toolchain=False,
    )
    assert session.gdb_args[0] == "my-special-gdb"


def test_build_invocation_passes_probe_kind_when_not_auto(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        probe_kind="jlink",
        require_toolchain=False,
    )
    assert "--probe" in session.server_args
    assert "jlink" in session.server_args


def test_build_invocation_omits_probe_when_auto(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        probe_kind="auto",
        require_toolchain=False,
    )
    assert "--probe" not in session.server_args


def test_build_invocation_returns_paths_as_strings(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        require_toolchain=False,
    )
    assert isinstance(session.elf, Path)
    assert all(isinstance(a, str) for a in session.server_args)
    assert all(isinstance(a, str) for a in session.gdb_args)


# ---------------------------------------------------------------------------
# Wave 2: lockfile-aware probe-rs + gdb resolution
# ---------------------------------------------------------------------------


def _seed_arm_gcc_with_gdb_in_store(
    tmp_path: Path,
    monkeypatch,
    *,
    version: str = "14.2.1-1.1",
) -> str:
    """Install a fake arm-none-eabi-gcc bundle (with gdb) into an
    isolated store; returns the sha256 the lockfile should pin.
    """
    import hashlib
    import tarfile

    from alloy_cli.core import toolchain_manager as _tm
    from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact

    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_store" / "tools"))

    src = tmp_path / "_pkg" / f"arm-{version}" / "bin"
    src.mkdir(parents=True, exist_ok=True)
    for binary in ("arm-none-eabi-gcc", "arm-none-eabi-gdb"):
        (src / binary).write_text("#!/bin/sh\n", encoding="utf-8")
    archive = tmp_path / f"arm-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tmp_path / "_pkg" / f"arm-{version}", arcname=f"arm-{version}")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()

    artefact = SourceArtifact(
        tool="arm-none-eabi-gcc",
        version=version,
        source="xpack",
        url=f"https://example.com/arm-{version}.tar.gz",
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir=f"arm-{version}",
        binaries=("bin/arm-none-eabi-gcc", "bin/arm-none-eabi-gdb"),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(artefact.url, archive)
    _tm.install(artefact, downloader=fake_dl)
    return sha


def _seed_lockfile_with_arm_gcc(project: Path, *, sha256: str, version: str = "14.2.1-1.1") -> None:
    from alloy_cli.core import lockfile_toolchain as _lf

    lock = _lf.add(_lf.empty(), "arm-none-eabi-gcc", version, sha256)
    _lf.write(project / ".alloy" / _lf.LOCKFILE_NAME, lock)


def test_build_invocation_resolves_gdb_via_lockfile_bundle(tmp_path, monkeypatch) -> None:
    """When the lockfile pins arm-none-eabi-gcc (which bundles
    arm-none-eabi-gdb), build_invocation returns the absolute store
    path to gdb — even though the lockfile doesn't mention gdb directly.
    """
    sha = _seed_arm_gcc_with_gdb_in_store(tmp_path, monkeypatch)
    project = tmp_path / "proj"
    project.mkdir()
    _seed_lockfile_with_arm_gcc(project, sha256=sha)

    elf = project / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        require_toolchain=False,
        project_root=project,
    )
    # gdb argv[0] is the absolute store path
    assert session.gdb_args[0].endswith("arm-none-eabi-gdb")
    assert "store" in session.gdb_args[0]


def test_build_invocation_without_lockfile_falls_back_to_path(tmp_path) -> None:
    """No lockfile → behaviour byte-identical to today (gdb argv[0]
    is just the bare binary name).
    """
    project = tmp_path / "proj"
    project.mkdir()
    elf = project / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        require_toolchain=False,
        project_root=project,
    )
    # Without a lockfile, gdb is the bare name
    assert session.gdb_args[0] == "arm-none-eabi-gdb"


def test_build_invocation_explicit_gdb_overrides_lockfile(tmp_path, monkeypatch) -> None:
    """--gdb-ui beats the lockfile: the user opting into a specific
    GDB knows what they want."""
    sha = _seed_arm_gcc_with_gdb_in_store(tmp_path, monkeypatch)
    project = tmp_path / "proj"
    project.mkdir()
    _seed_lockfile_with_arm_gcc(project, sha256=sha)

    elf = project / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        gdb_ui="echo",  # any binary on PATH (echo always exists)
        require_toolchain=False,
        project_root=project,
    )
    assert session.gdb_args[0] == "echo"


def test_build_invocation_resolves_probe_rs_via_lockfile(tmp_path, monkeypatch) -> None:
    """The gdb-server's probe-rs invocation also routes through the
    lockfile resolver."""
    import hashlib
    import tarfile

    from alloy_cli.core import lockfile_toolchain as _lf
    from alloy_cli.core import toolchain_manager as _tm
    from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact

    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_store" / "tools"))

    src = tmp_path / "_pkg" / "probe-rs-tools-0.27.0"
    src.mkdir(parents=True)
    (src / "probe-rs").write_text("#!/bin/sh\n", encoding="utf-8")
    archive = tmp_path / "probe-rs-0.27.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname="probe-rs-tools-0.27.0")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()

    artefact = SourceArtifact(
        tool="probe-rs",
        version="0.27.0",
        source="probe-rs",
        url="https://example.com/probe-rs-0.27.0.tar.gz",
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir="probe-rs-tools-0.27.0",
        binaries=("probe-rs",),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(artefact.url, archive)
    _tm.install(artefact, downloader=fake_dl)

    project = tmp_path / "proj"
    project.mkdir()
    lock = _lf.add(_lf.empty(), "probe-rs", "0.27.0", sha)
    _lf.write(project / ".alloy" / _lf.LOCKFILE_NAME, lock)

    elf = project / "firmware.elf"
    elf.write_bytes(b"")
    session = build_invocation(
        elf=elf,
        chip="stm32g071rb",
        require_toolchain=False,
        project_root=project,
    )
    assert session.server_args[0].endswith("probe-rs")
    assert "store" in session.server_args[0]


def test_build_invocation_lockfile_pin_missing_from_store_raises(
    tmp_path, monkeypatch
) -> None:
    """Lockfile pins probe-rs / arm-gcc but the store has nothing →
    typed version-mismatch error before any process is composed."""
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_empty" / "tools"))
    from alloy_cli.core import lockfile_toolchain as _lf
    from alloy_cli.core.errors import (
        FamilyToolchainInstallerVersionMismatchError,
    )

    project = tmp_path / "proj"
    project.mkdir()
    lock = _lf.add(_lf.empty(), "probe-rs", "0.27.0", "0" * 64)
    _lf.write(project / ".alloy" / _lf.LOCKFILE_NAME, lock)

    import pytest

    elf = project / "firmware.elf"
    elf.write_bytes(b"")
    with pytest.raises(FamilyToolchainInstallerVersionMismatchError):
        build_invocation(
            elf=elf,
            chip="stm32g071rb",
            require_toolchain=False,
            project_root=project,
        )
