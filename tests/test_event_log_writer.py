"""Tests for ``add-event-log-writer`` (#24).

Phase 4 covers:

- :class:`core.events.EventLogger` round-trip + rotation (4.1).
- Each mutating core op produces the expected event shape
  (4.2).
- The Dashboard activity panel renders the most-recent event
  after a TUI mutation lands (4.3).
- MCP `apply_diff` followed by `list_recent_events` surfaces
  the same record (4.4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import events as _events
from alloy_cli.core.events import MAX_LINES, EventLogger, EventRecord, record_event
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    AlloyDir,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.main import cli
from alloy_cli.mcp import build_default_registry

# ---------------------------------------------------------------------------
# Phase 4.1 — EventLogger round-trip
# ---------------------------------------------------------------------------


def test_event_logger_appends_one_record(tmp_path: Path) -> None:
    layout = AlloyDir(root=tmp_path)
    logger = EventLogger(layout=layout)
    logger.append(
        EventRecord(timestamp="2026-05-02T18:00:00+00:00", event="foo", payload={"k": "v"})
    )
    body = logger.path.read_text(encoding="utf-8").splitlines()
    assert len(body) == 1
    parsed = json.loads(body[0])
    assert parsed["event"] == "foo"
    assert parsed["payload"] == {"k": "v"}


def test_record_event_helper_swallows_oserror(tmp_path: Path, monkeypatch) -> None:
    """A failing append must never crash the caller."""

    def _explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(EventLogger, "append", _explode)
    # Should return cleanly, not raise.
    record_event(tmp_path, "foo", k="v")


def test_event_logger_rotates_after_max_lines(tmp_path: Path) -> None:
    layout = AlloyDir(root=tmp_path)
    logger = EventLogger(layout=layout)
    layout.ensure()
    # Pre-fill with MAX_LINES synthetic entries so the next
    # append triggers rotation.
    with logger.path.open("w", encoding="utf-8") as fp:
        for i in range(MAX_LINES):
            fp.write(json.dumps({"timestamp": "x", "event": f"e{i}", "payload": {}}) + "\n")

    logger.append(EventRecord(timestamp="now", event="rolled", payload={}))

    rolled_lines = logger.rolled_path.read_text(encoding="utf-8").splitlines()
    fresh_lines = logger.path.read_text(encoding="utf-8").splitlines()
    assert len(rolled_lines) == MAX_LINES
    assert len(fresh_lines) == 1
    assert json.loads(fresh_lines[0])["event"] == "rolled"


# ---------------------------------------------------------------------------
# Phase 4.2 — mutating core ops emit events
# ---------------------------------------------------------------------------


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


def _read_events(root: Path) -> list[dict]:
    layout = AlloyDir(root=root)
    path = layout.cache / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_build_run_emits_started_and_finished(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    fake.expect(["cmake", "--build"], returncode=0)

    from alloy_cli.core import build as _build

    _build.run(
        project_root=tmp_path,
        profile="debug",
        runner=fake,
        require_toolchain=False,
        skip_codegen=True,
    )

    events = _read_events(tmp_path)
    types = [e["event"] for e in events]
    assert "build_started" in types
    assert "build_finished" in types


def test_failed_build_still_emits_finished(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=1, stderr="cmake: bad target")

    from alloy_cli.core import build as _build

    _build.run(
        project_root=tmp_path,
        profile="debug",
        runner=fake,
        require_toolchain=False,
        skip_codegen=True,
    )

    events = _read_events(tmp_path)
    finished = [e for e in events if e["event"] == "build_finished"]
    assert len(finished) == 1
    assert finished[0]["payload"]["returncode"] != 0


def test_flash_run_emits_started_and_finished(tmp_path: Path) -> None:
    """Flash with FakeRunner emits both lifecycle events."""
    _seed_project(tmp_path)
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")

    fake = FakeRunner()
    fake.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps([{"type": "stlink", "serial_number": "abc"}]),
    )
    fake.expect(["probe-rs", "run"], returncode=0, stdout="Done")

    from alloy_cli.core import flash as _flash

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
    _flash.run(
        elf=elf,
        config=config,
        runner=fake,
        require_toolchain=False,
        project_root=tmp_path,
    )

    types = [e["event"] for e in _read_events(tmp_path)]
    assert "flash_started" in types
    assert "flash_finished" in types


def test_alloy_add_uart_writes_peripheral_added(tmp_path: Path, patched_ir) -> None:
    """CLI `alloy add uart --apply` records the event."""
    _seed_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "add",
            "uart",
            "--name",
            "console",
            "--peripheral",
            "USART1",
            "--tx",
            "PA9",
            "--rx",
            "PA10",
            "--apply",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    events = _read_events(tmp_path)
    added = [e for e in events if e["event"] == "peripheral_added"]
    assert len(added) == 1
    assert added[0]["payload"]["kind"] == "uart"
    assert added[0]["payload"]["name"] == "console"


@pytest.fixture
def patched_ir(monkeypatch):
    """Mirror the fixture used in test_mcp_server / test_command_add."""
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
        ),
        pins=(
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
        ),
        connection_candidates=(
            ConnectionCandidateView(
                pin="PA9", peripheral="USART1", signal="TX", af_number=1
            ),
            ConnectionCandidateView(
                pin="PA10", peripheral="USART1", signal="RX", af_number=1
            ),
        ),
        dma_routes=(),
        clock_nodes=(),
        package=None,
        payload={},
    )
    monkeypatch.setattr(_ir, "load_device", lambda *_args, **_kw: fixture)


# ---------------------------------------------------------------------------
# Phase 4.3 — Dashboard activity panel reflects events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_activity_renders_peripheral_added(tmp_path: Path) -> None:
    """A `peripheral_added` event surfaces in the activity panel."""
    _seed_project(tmp_path)
    record_event(tmp_path, "peripheral_added", kind="gpio", name="led")

    from alloy_cli.tui.app import TuiApp
    from alloy_cli.tui.screens.dashboard import DashboardScreen

    screen = DashboardScreen(project_dir=tmp_path)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()

        activity_panel = screen.query_one("#dash-activity")
        rendered = " ".join(
            str(node.render()) for node in activity_panel.query("Static")
        )
        assert "peripheral_added" in rendered
        assert "led" in rendered


# ---------------------------------------------------------------------------
# Phase 4.4 — MCP apply_diff produces a record
# ---------------------------------------------------------------------------


def test_mcp_apply_diff_emits_peripheral_added(tmp_path: Path, patched_ir) -> None:
    _seed_project(tmp_path)
    registry = build_default_registry(project_dir=tmp_path)
    preview = registry.call(
        "preview_diff",
        kind="uart",
        name="console",
        payload={"peripheral": "USART1", "tx": "PA9", "rx": "PA10"},
    )
    diff_id = preview["diff_id"]
    assert diff_id is not None
    registry.call("apply_diff", diff_id=diff_id)

    events = _read_events(tmp_path)
    added = [e for e in events if e["event"] == "peripheral_added"]
    assert len(added) == 1
    assert added[0]["payload"]["kind"] == "uart"

    # And `list_recent_events` surfaces the same record.
    recent = registry.call("list_recent_events", limit=5)
    assert any(r["event"] == "peripheral_added" for r in recent)


def test_record_event_uses_module_constants() -> None:
    """Tiny smoke test so the public API stays exported."""
    assert _events.MAX_LINES == 1024
    assert hasattr(_events, "record_event")
