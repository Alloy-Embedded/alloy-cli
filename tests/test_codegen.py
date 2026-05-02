"""Tests for ``alloy_cli.core.codegen`` — codegen integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alloy_cli.core import codegen as _codegen
from alloy_cli.core.codegen import (
    CodegenEntry,
    CodegenError,
    discover_codegen_entry,
    force_regenerate,
    regenerate_if_stale,
)
from alloy_cli.core.project import (
    AlloyDir,
    BoardRef,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _chip_config() -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


def _board_config() -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=BoardRef(id="nucleo_g071rb"),
        chip=None,
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


class _FakeCallable:
    """Stand-in for ``alloy_codegen.generate``: writes one .hpp into out_dir."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, config: ProjectConfig, out_dir: Path) -> None:
        self.calls += 1
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "include").mkdir(exist_ok=True)
        (out_dir / "include" / "device.hpp").write_text(
            f"// generated for {config.project.name}\n",
            encoding="utf-8",
        )


def _entry(version: str = "1.2.3") -> CodegenEntry:
    return CodegenEntry(version=version, callable=_FakeCallable())


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discover_returns_none_when_alloy_codegen_missing(monkeypatch) -> None:
    def _raising_import(name: str) -> None:
        if name == "alloy_codegen":
            raise ImportError(name)
        return None

    monkeypatch.setattr("alloy_cli.core.codegen.importlib.import_module", _raising_import)
    assert discover_codegen_entry() is None


def test_discover_returns_none_when_generate_attribute_missing(monkeypatch) -> None:
    class _ModuleStub:
        __version__ = "0.1.0"

    monkeypatch.setattr(
        "alloy_cli.core.codegen.importlib.import_module",
        lambda name: _ModuleStub() if name == "alloy_codegen" else None,
    )
    assert discover_codegen_entry() is None


def test_discover_returns_entry_with_version_and_callable(monkeypatch) -> None:
    class _ModuleStub:
        __version__ = "0.4.2"

        @staticmethod
        def generate(config, out_dir):
            return None

    monkeypatch.setattr(
        "alloy_cli.core.codegen.importlib.import_module",
        lambda name: _ModuleStub() if name == "alloy_codegen" else None,
    )
    entry = discover_codegen_entry()
    assert entry is not None
    assert entry.version == "0.4.2"
    assert callable(entry.callable)


# ---------------------------------------------------------------------------
# regenerate_if_stale
# ---------------------------------------------------------------------------


def test_regenerate_runs_when_stamp_missing(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    entry = _entry()
    result = regenerate_if_stale(_chip_config(), layout, entry=entry)
    assert result.skipped is False
    assert result.returncode == 0
    assert any(p.name == "device.hpp" for p in result.written)
    stamp = (layout.generated / "st_stm32g0_stm32g071rb" / ".stamp").read_text(encoding="utf-8")
    payload = json.loads(stamp)
    assert payload["codegen_version"] == "1.2.3"


def test_regenerate_skips_when_stamp_fresh(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    entry = _entry()
    first = regenerate_if_stale(_chip_config(), layout, entry=entry)
    assert first.skipped is False
    fake = entry.callable
    assert fake.calls == 1  # type: ignore[attr-defined]
    second = regenerate_if_stale(_chip_config(), layout, entry=entry)
    assert second.skipped is True
    assert second.returncode == 0
    assert fake.calls == 1  # type: ignore[attr-defined]


def test_regenerate_runs_when_codegen_version_changes(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    first_entry = _entry(version="1.0.0")
    regenerate_if_stale(_chip_config(), layout, entry=first_entry)
    second_entry = _entry(version="1.0.1")
    second_callable = second_entry.callable
    second = regenerate_if_stale(_chip_config(), layout, entry=second_entry)
    assert second.skipped is False
    assert second_callable.calls == 1  # type: ignore[attr-defined]


def test_regenerate_skipped_with_reason_when_entry_is_none(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    result = regenerate_if_stale(_chip_config(), layout, entry=None)
    assert result.returncode is None
    assert result.skipped is True
    assert "not-installed" in result.reason


def test_regenerate_handles_codegen_exception(tmp_path) -> None:
    class _Bad:
        def __call__(self, _config, _out_dir):
            raise RuntimeError("boom")

    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    entry = CodegenEntry(version="9.9.9", callable=_Bad())
    result = regenerate_if_stale(_chip_config(), layout, entry=entry)
    assert result.returncode == 1
    assert "boom" in result.reason


# ---------------------------------------------------------------------------
# force_regenerate
# ---------------------------------------------------------------------------


def test_force_regenerate_ignores_fresh_stamp(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    entry = _entry()
    regenerate_if_stale(_chip_config(), layout, entry=entry)
    assert entry.callable.calls == 1  # type: ignore[attr-defined]
    result = force_regenerate(_chip_config(), layout, entry=entry)
    assert result.skipped is False
    assert entry.callable.calls == 2  # type: ignore[attr-defined]


def test_force_regenerate_raises_when_codegen_not_installed(tmp_path, monkeypatch) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    monkeypatch.setattr(_codegen, "discover_codegen_entry", lambda: None)
    with pytest.raises(CodegenError, match="alloy-codegen"):
        force_regenerate(_chip_config(), layout)


# ---------------------------------------------------------------------------
# Device label edge cases
# ---------------------------------------------------------------------------


def test_board_only_project_uses_board_label(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    entry = _entry()
    regenerate_if_stale(_board_config(), layout, entry=entry)
    assert (layout.generated / "board_nucleo_g071rb" / ".stamp").exists()
