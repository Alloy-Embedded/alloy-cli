"""Tests for the MCP tool registry + stdio server fallback."""

from __future__ import annotations

import json
import subprocess
import time
from io import StringIO
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.main import cli
from alloy_cli.mcp import (
    DiffCache,
    Tool,
    ToolError,
    ToolRegistry,
    build_default_registry,
)
from alloy_cli.mcp.server import _list_tools, serve_stdio_fallback

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_project(root: Path, *, peripherals: tuple[PeripheralEntry, ...] = ()) -> None:
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={"profile": "default_pll_64mhz"},
        peripherals=peripherals,
        build={},
        flash={},
        raw={},
    )
    write(root / PROJECT_FILE, config)


@pytest.fixture
def patched_ir(monkeypatch):
    from alloy_cli.core import ir as _ir
    from alloy_cli.core.ir import (
        ConnectionCandidateView,
        DeviceIdentity,
        DeviceIR,
        PeripheralView,
        PinView,
    )

    fixture = DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32g0",
            device="stm32g071rb",
            package="lqfp64",
            core="cortex-m0plus",
            summary="STM32G0",
        ),
        peripherals=(
            PeripheralView(name="USART1", ip_name="uart", ip_version=None, base_address=0),
            PeripheralView(name="USART2", ip_name="uart", ip_version=None, base_address=0),
        ),
        pins=(
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
            PinView(name="PA5", port="A", number=5),
        ),
        connection_candidates=(
            ConnectionCandidateView(pin="PA9", peripheral="USART1", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA10", peripheral="USART1", signal="RX", af_number=1),
        ),
        dma_routes=(),
        clock_nodes=(),
        payload={},
    )
    monkeypatch.setattr(_ir, "load_device", lambda *a, **kw: fixture)
    yield fixture


# ---------------------------------------------------------------------------
# DiffCache
# ---------------------------------------------------------------------------


def test_diff_cache_round_trip() -> None:
    from alloy_cli.core.diagnostics import FilePatch, UnifiedDiff

    cache = DiffCache(ttl_seconds=5)
    diff = UnifiedDiff(patches=(FilePatch(path=Path("a.txt"), before="x", after="y"),))
    diff_id = cache.store(diff, {"hint": "x"})
    fetched = cache.fetch(diff_id)
    assert fetched.diff is diff
    assert fetched.proposed_summary == {"hint": "x"}
    cache.discard(diff_id)
    with pytest.raises(ToolError):
        cache.fetch(diff_id)


def test_diff_cache_expires() -> None:
    from alloy_cli.core.diagnostics import FilePatch, UnifiedDiff
    from alloy_cli.core.errors import StaleDiffError

    cache = DiffCache(ttl_seconds=0.01)
    diff = UnifiedDiff(patches=(FilePatch(path=Path("a.txt"), before="x", after="y"),))
    diff_id = cache.store(diff, {})
    time.sleep(0.05)
    with pytest.raises(StaleDiffError):
        cache.fetch(diff_id)


# ---------------------------------------------------------------------------
# ToolRegistry / default registry shape
# ---------------------------------------------------------------------------


def test_default_registry_lists_required_tools(tmp_path) -> None:
    registry = build_default_registry(project_dir=tmp_path)
    names = set(registry.names())
    required = {
        "list_boards",
        "list_devices",
        "query_device_ir",
        "suggest_pins",
        "read_alloy_toml",
        "preview_diff",
        "apply_diff",
        "add_uart",
        "add_gpio",
        "add_spi",
        "add_i2c",
        "set_clock_profile",
        "build",
        "flash",
    }
    assert required <= names


def test_every_tool_has_non_empty_description(tmp_path) -> None:
    registry = build_default_registry(project_dir=tmp_path)
    for name in registry.names():
        tool = registry.get_tool(name)
        assert tool.description.strip(), f"Tool {name} missing description"


def test_register_rejects_empty_description(tmp_path) -> None:
    registry = ToolRegistry(project_dir=tmp_path, runner=FakeRunner())
    with pytest.raises(ValueError):
        registry.register(
            Tool(name="bad", description="", handler=lambda r: None, parameter_schema={})
        )


def test_unknown_tool_returns_tool_error(tmp_path) -> None:
    registry = build_default_registry(project_dir=tmp_path)
    with pytest.raises(ToolError) as exc_info:
        registry.call("does-not-exist")
    assert exc_info.value.error_type == "tool-not-found"


# ---------------------------------------------------------------------------
# Tool semantics
# ---------------------------------------------------------------------------


def test_read_alloy_toml_returns_decoded_payload(tmp_path) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path)
    result = registry.call("read_alloy_toml")
    assert result["project"]["name"] == "firmware"
    assert result["chip"]["device"] == "stm32g071rb"
    assert result["clocks"]["profile"] == "default_pll_64mhz"


def test_preview_diff_caches_diff_id(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path)
    result = registry.call("preview_diff", kind="uart", name="console")
    assert result["diff_id"]
    assert "+++ b/alloy.toml" in result["diff_text"]


def test_apply_diff_writes_files(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path)
    preview = registry.call("preview_diff", kind="uart", name="console")
    diff_id = preview["diff_id"]
    applied = registry.call("apply_diff", diff_id=diff_id)
    assert applied["applied"] is True
    assert "alloy.toml" in applied["written"]
    # Diff is consumed on apply.
    with pytest.raises(ToolError):
        registry.call("apply_diff", diff_id=diff_id)


def test_add_gpio_with_invalid_pin_returns_validation_summary(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path)
    result = registry.call("add_gpio", name="led", pin="PA999", mode="output")
    assert result["has_errors"] is True
    codes = [d["code"] for d in result["diagnostics"]]
    assert "unknown-pin" in codes
    assert result["diff_id"] is None


def test_apply_diff_unknown_id_raises_tool_error(tmp_path) -> None:
    registry = build_default_registry(project_dir=tmp_path)
    with pytest.raises(ToolError):
        registry.call("apply_diff", diff_id="nope")


def test_set_clock_profile_caches_diff(tmp_path) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path)
    result = registry.call("set_clock_profile", profile="custom_profile")
    assert result["diff_id"]
    assert "custom_profile" in result["diff_text"]


def test_default_registry_lists_regenerate_tool(tmp_path) -> None:
    registry = build_default_registry(project_dir=tmp_path)
    assert "regenerate" in registry.names()
    descriptor = registry.get_tool("regenerate")
    assert descriptor.description.strip()


def test_regenerate_tool_raises_when_alloy_codegen_missing(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: None)
    registry = build_default_registry(project_dir=tmp_path)
    with pytest.raises(ToolError) as exc_info:
        registry.call("regenerate")
    assert exc_info.value.error_type == "codegen-not-installed"


def test_regenerate_tool_writes_files_and_stamp(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)
    from alloy_cli.core.codegen import CodegenEntry

    def _generate(_config, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "device.hpp").write_text("// ok\n", encoding="utf-8")

    entry = CodegenEntry(version="0.4.2", callable=_generate)
    monkeypatch.setattr("alloy_cli.core.codegen.discover_codegen_entry", lambda: entry)

    registry = build_default_registry(project_dir=tmp_path)
    result = registry.call("regenerate")
    assert result["returncode"] == 0
    assert any("device.hpp" in path for path in result["written"])
    stamp = tmp_path / ".alloy" / "generated" / "st_stm32g0_stm32g071rb" / ".stamp"
    assert stamp.exists()


def test_build_tool_surfaces_codegen_returncode(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)
    monkeypatch.setattr(
        "alloy_cli.core.codegen.discover_codegen_entry",
        lambda: None,
    )
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)

    from alloy_cli.core import process as _process

    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)
    registry = ToolRegistry(project_dir=tmp_path, runner=fake)
    # Re-register the standard tools but with our runner.
    from alloy_cli.mcp import build_default_registry as _build_default

    base = _build_default(project_dir=tmp_path, runner=fake)
    base.diff_cache = registry.diff_cache  # share TTL-free cache for the test
    result = base.call("build")
    assert result["ok"] is True
    assert result["codegen_returncode"] is None
    assert result["codegen_skipped"] is True
    del _process  # quiet the linter


def test_list_boards_query_filters_results(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "boards"
    catalog.mkdir()
    (catalog / "nucleo_g071rb").mkdir()
    (catalog / "nucleo_g071rb" / "board.json").write_text(
        json.dumps(
            {
                "board_id": "nucleo_g071rb",
                "vendor": "st",
                "family": "stm32g0",
                "device": "stm32g071rb",
                "arch": "cortex-m0plus",
                "mcu": "STM32G071RBT6",
                "flash_size_bytes": 131072,
                "summary": "ST Nucleo G071RB",
                "tier": 1,
                "clock_profiles": ["pll_64mhz"],
            }
        )
    )
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(catalog))
    from alloy_cli.core import boards as _boards
    from alloy_cli.core import search as _search

    _boards.load_catalog.cache_clear()
    _search.reset_caches()

    registry = build_default_registry(project_dir=tmp_path)
    result = registry.call("list_boards", query="nucleo")
    assert any(b["board_id"] == "nucleo_g071rb" for b in result)


# ---------------------------------------------------------------------------
# stdio fallback server
# ---------------------------------------------------------------------------


def test_list_tools_emits_schema_for_every_handler(tmp_path) -> None:
    registry = build_default_registry(project_dir=tmp_path)
    schema = _list_tools(registry)
    by_name = {entry["name"]: entry for entry in schema}
    assert "list_boards" in by_name
    assert by_name["list_boards"]["description"]
    assert isinstance(by_name["list_boards"]["parameters"], dict)


def test_serve_stdio_fallback_round_trips_list_tools(tmp_path, monkeypatch, capsys) -> None:
    # Inject a stdin with a single list_tools request and run the loop.
    payload = json.dumps({"method": "list_tools"}) + "\n"
    monkeypatch.setattr("sys.stdin", StringIO(payload))
    registry = build_default_registry(project_dir=tmp_path)
    serve_stdio_fallback(registry)
    captured = capsys.readouterr()
    decoded = json.loads(captured.out.strip().splitlines()[0])
    assert {entry["name"] for entry in decoded["tools"]}.issuperset({"list_boards", "preview_diff"})


def test_serve_stdio_fallback_call_tool_round_trip(tmp_path, monkeypatch, capsys) -> None:
    _seed_project(tmp_path)
    payload = json.dumps({"method": "call_tool", "name": "read_alloy_toml", "arguments": {}}) + "\n"
    monkeypatch.setattr("sys.stdin", StringIO(payload))
    registry = build_default_registry(project_dir=tmp_path)
    serve_stdio_fallback(registry)
    captured = capsys.readouterr()
    decoded = json.loads(captured.out.strip().splitlines()[0])
    assert decoded["result"]["project"]["name"] == "firmware"


def test_serve_stdio_fallback_unknown_tool_emits_error(tmp_path, monkeypatch, capsys) -> None:
    payload = json.dumps({"method": "call_tool", "name": "missing", "arguments": {}}) + "\n"
    monkeypatch.setattr("sys.stdin", StringIO(payload))
    registry = build_default_registry(project_dir=tmp_path)
    serve_stdio_fallback(registry)
    captured = capsys.readouterr()
    decoded = json.loads(captured.out.strip().splitlines()[0])
    assert decoded["error"]["error_type"] == "tool-not-found"


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_alloy_mcp_help_lists_serve() -> None:
    result = CliRunner().invoke(cli, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


def test_alloy_mcp_serve_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["mcp", "serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
    assert "--cwd" in result.output


def test_alloy_mcp_serve_rejects_http_until_sdk_lands() -> None:
    result = CliRunner().invoke(cli, ["mcp", "serve", "--transport", "http"])
    assert result.exit_code != 0
    assert "alloy-cli[mcp]" in result.output


def test_alloy_mcp_serve_stdio_round_trips_via_subprocess(tmp_path) -> None:
    _seed_project(tmp_path)
    request = json.dumps({"method": "call_tool", "name": "read_alloy_toml", "arguments": {}}) + "\n"
    proc = subprocess.run(
        ["alloy", "mcp", "serve", "--cwd", str(tmp_path)],
        input=request,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    decoded = json.loads(proc.stdout.strip().splitlines()[0])
    assert decoded["result"]["project"]["name"] == "firmware"
