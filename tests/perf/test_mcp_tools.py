"""MCP tool-call latency benchmarks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.mcp import build_default_registry
from tests.perf._budgets import effective_budget


def _seed_project(root: Path) -> None:
    config = ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(root / PROJECT_FILE, config)


@pytest.mark.perf
def test_list_boards_call_under_budget(benchmark, tmp_path: Path) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())

    # Warm
    registry.call("list_boards")

    def _invoke() -> None:
        registry.call("list_boards")

    benchmark(_invoke)
    assert benchmark.stats["mean"] < effective_budget("MCP tool call"), (
        f"mcp list_boards mean {benchmark.stats['mean']:.3f}s "
        f"exceeded budget {effective_budget('mcp tool call'):.3f}s"
    )


@pytest.mark.perf
def test_read_alloy_toml_call_under_budget(benchmark, tmp_path: Path) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())

    def _invoke() -> None:
        result = registry.call("read_alloy_toml")
        assert result["project"]["name"] == "firmware"

    benchmark(_invoke)
    assert benchmark.stats["mean"] < effective_budget("MCP tool call")


@pytest.mark.perf
def test_list_recent_events_call_under_budget(benchmark, tmp_path: Path) -> None:
    _seed_project(tmp_path)
    # Pre-populate a few events so the tool actually walks the file.
    layout = tmp_path / ".alloy" / "cache"
    layout.mkdir(parents=True, exist_ok=True)
    (layout / "events.jsonl").write_text(
        "\n".join(
            json.dumps({"timestamp": f"t{i}", "event": "noop", "payload": {}})
            for i in range(10)
        )
        + "\n",
        encoding="utf-8",
    )
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())

    def _invoke() -> None:
        registry.call("list_recent_events", limit=5)

    benchmark(_invoke)
    assert benchmark.stats["mean"] < effective_budget("MCP tool call")
