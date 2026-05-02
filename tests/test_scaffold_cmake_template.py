"""Tests for the FetchContent-wired CMakeLists template (#wire-alloy-hal-fetchcontent)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core.scaffold import (
    ScaffoldError,
    ScaffoldRequest,
    scaffold,
)
from alloy_cli.main import cli
from tests.snapshots._render import seed_board_catalog


@pytest.fixture
def board_catalog(tmp_path: Path) -> Path:
    """Plant a stub catalog so scaffold() can resolve nucleo_g071rb."""
    seed_board_catalog(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Board-driven scaffold writes the FetchContent + helper invocations
# ---------------------------------------------------------------------------


def _scaffold_board(name: str, dest: Path) -> Path:
    request = ScaffoldRequest(
        name=name,
        destination=dest,
        board_id="nucleo_g071rb",
        device=None,
        license="MIT",
        author="Alloy User",
        init_git=False,
        force=True,
    )
    scaffold(request)
    return dest / "CMakeLists.txt"


def test_template_includes_fetchcontent_declare(tmp_path: Path, board_catalog: Path) -> None:
    cmakelists = _scaffold_board("fcsmoke", tmp_path / "fcsmoke")
    body = cmakelists.read_text(encoding="utf-8")
    assert "include(FetchContent)" in body
    assert "FetchContent_Declare(alloy" in body
    assert "FetchContent_MakeAvailable(alloy)" in body


def test_template_uses_alloy_add_runtime_executable(tmp_path: Path, board_catalog: Path) -> None:
    cmakelists = _scaffold_board("fcsmoke", tmp_path / "fcsmoke")
    body = cmakelists.read_text(encoding="utf-8")
    assert "alloy_add_runtime_executable(${ALLOY_PROJECT_NAME}" in body


def test_template_passes_board_id_through(tmp_path: Path, board_catalog: Path) -> None:
    cmakelists = _scaffold_board("fcsmoke", tmp_path / "fcsmoke")
    body = cmakelists.read_text(encoding="utf-8")
    assert 'set(ALLOY_BOARD "${ALLOY_BOARD_ID}"' in body


def test_template_supports_local_source_override(tmp_path: Path, board_catalog: Path) -> None:
    cmakelists = _scaffold_board("fcsmoke", tmp_path / "fcsmoke")
    body = cmakelists.read_text(encoding="utf-8")
    # The template MUST give contributors an escape hatch from the
    # network round-trip; ALLOY_SOURCE_OVERRIDE is the canonical name.
    assert "ALLOY_SOURCE_OVERRIDE" in body


def test_template_pins_alloy_via_resolve_helper(tmp_path: Path, board_catalog: Path) -> None:
    cmakelists = _scaffold_board("fcsmoke", tmp_path / "fcsmoke")
    body = cmakelists.read_text(encoding="utf-8")
    assert "alloy_cli_resolve_alloy_tag(ALLOY_GIT_TAG)" in body


def test_template_keeps_alloy_cli_link_call(tmp_path: Path, board_catalog: Path) -> None:
    cmakelists = _scaffold_board("fcsmoke", tmp_path / "fcsmoke")
    body = cmakelists.read_text(encoding="utf-8")
    assert "alloy_cli_link(${ALLOY_PROJECT_NAME})" in body


# ---------------------------------------------------------------------------
# Chip-only path is rejected with a clear error
# ---------------------------------------------------------------------------


def test_scaffold_chip_only_raises_with_followup_hint(tmp_path: Path) -> None:
    request = ScaffoldRequest(
        name="chiponly",
        destination=tmp_path / "chiponly",
        board_id=None,
        device=("st", "stm32g0", "stm32g071rb"),
        license="MIT",
        author="Alloy User",
        init_git=False,
        force=True,
    )
    with pytest.raises(ScaffoldError) as exc:
        scaffold(request)
    msg = str(exc.value)
    assert "chip-only" in msg.lower()
    assert "wire-chip-only-projects" in msg


def test_alloy_new_device_path_surfaces_clean_error(tmp_path: Path) -> None:
    """`alloy new --device` flows through ScaffoldError → click exit 1."""
    seed_board_catalog(tmp_path)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "new",
                "chiponly",
                "--device",
                "st/stm32g0/stm32g071rb",
                "--no-git",
            ],
        )
    assert result.exit_code != 0
    assert "chip-only" in result.output.lower()


# ---------------------------------------------------------------------------
# AlloyCli.cmake helpers
# ---------------------------------------------------------------------------


def _alloy_cli_cmake_text() -> str:
    """Read AlloyCli.cmake from either the dev checkout or the wheel layout."""
    candidates = [
        Path(__file__).resolve().parents[1] / "cmake" / "AlloyCli.cmake",
        Path(__file__).resolve().parents[1] / "src" / "alloy_cli" / "cmake" / "AlloyCli.cmake",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "AlloyCli.cmake not found in dev checkout or wheel-layout locations"
    )


def test_alloy_cli_cmake_defines_resolve_helper() -> None:
    """The resolve-tag helper that the template calls must exist."""
    body = _alloy_cli_cmake_text()
    assert "function(alloy_cli_resolve_alloy_tag" in body


def test_alloy_cli_link_warns_when_hal_missing() -> None:
    """alloy_cli_link MUST warn (not fail) when Alloy::hal isn't a target."""
    body = _alloy_cli_cmake_text()
    assert "Alloy::hal is missing" in body
