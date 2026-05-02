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
