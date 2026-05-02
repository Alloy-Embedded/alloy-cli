"""Shared render helpers for snapshot tests + the docs gallery generator.

Both ``tests/test_snapshots.py`` and
``scripts/generate_docs_images.py`` reach into here so a single
seed → IR → screen → SVG pipeline drives both surfaces.  That
keeps the spec contract honest: ``docs/images/<n>.svg`` matches
``tests/snapshots/<n>.svg`` byte-for-byte.

The helpers live as plain functions (not pytest fixtures) so the
script can call them without bringing pytest in.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path

from rich.console import Console

from alloy_cli.core.ir import (
    ClockNodeView,
    ConnectionCandidateView,
    DeviceIdentity,
    DeviceIR,
    PeripheralView,
    PinView,
)
from alloy_cli.core.project import (
    BoardRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
)
from alloy_cli.tui.app import TuiApp

# ---------------------------------------------------------------------------
# Board catalog
# ---------------------------------------------------------------------------


def seed_board_catalog(tmp_root: Path) -> None:
    """Plant a 3-board stub catalog under ``tmp_root/boards``."""
    catalog = tmp_root / "boards"
    catalog.mkdir(parents=True, exist_ok=True)

    (catalog / "nucleo_g071rb").mkdir(exist_ok=True)
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
                "summary": "ST Nucleo-G071RB development board",
                "tier": 1,
                "clock_profiles": ["pll_64mhz", "hsi_16mhz"],
                "uart": {
                    "debug": {
                        "peripheral": "USART2",
                        "tx": "PA2",
                        "rx": "PA3",
                        "baud": 115200,
                    }
                },
                "leds": [{"name": "ld4", "pin": "PA5"}],
            }
        )
    )

    (catalog / "stm32f4_disco").mkdir(exist_ok=True)
    (catalog / "stm32f4_disco" / "board.json").write_text(
        json.dumps(
            {
                "board_id": "stm32f4_disco",
                "vendor": "st",
                "family": "stm32f4",
                "device": "stm32f407vg",
                "arch": "cortex-m4",
                "mcu": "STM32F407VGT6",
                "flash_size_bytes": 1048576,
                "summary": "STM32F4 Discovery — Cortex-M4 with USB OTG",
                "tier": 1,
                "clock_profiles": ["pll_168mhz"],
                "usb": {"otg": "fs"},
                "leds": [{"name": "ld5", "pin": "PD12"}],
            }
        )
    )

    (catalog / "rpi_pico").mkdir(exist_ok=True)
    (catalog / "rpi_pico" / "board.json").write_text(
        json.dumps(
            {
                "board_id": "rpi_pico",
                "vendor": "rp",
                "family": "rp2040",
                "device": "rp2040",
                "arch": "cortex-m0plus",
                "mcu": "RP2040",
                "flash_size_bytes": 2097152,
                "summary": "Raspberry Pi Pico — dual-core Cortex-M0+",
                "tier": 1,
                "clock_profiles": ["default_125mhz"],
                "leds": [{"name": "led", "pin": "GPIO25"}],
            }
        )
    )

    os.environ["ALLOY_BOARDS_ROOT"] = str(catalog)
    from alloy_cli.core import boards as _boards
    from alloy_cli.core import search as _search

    _boards.load_catalog.cache_clear()
    _search.reset_caches()


# ---------------------------------------------------------------------------
# Synthetic IR
# ---------------------------------------------------------------------------


def make_ir() -> DeviceIR:
    """Return a deterministic ``DeviceIR`` used by every TUI snapshot."""
    return DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32g0",
            device="stm32g071rb",
            package="lqfp64",
            core="cortex-m0plus",
            summary="STM32G0 series — Cortex-M0+ at up to 64 MHz",
        ),
        peripherals=(
            PeripheralView(
                name="USART1", ip_name="uart", ip_version="2.0", base_address=0x4001_3800
            ),
            PeripheralView(
                name="USART2", ip_name="uart", ip_version="2.0", base_address=0x4000_4400
            ),
            PeripheralView(
                name="SPI1", ip_name="spi", ip_version="2.0", base_address=0x4001_3000
            ),
            PeripheralView(
                name="I2C1", ip_name="i2c", ip_version="2.0", base_address=0x4000_5400
            ),
        ),
        pins=(
            PinView(name="PA0", port="A", number=0),
            PinView(name="PA1", port="A", number=1),
            PinView(name="PA2", port="A", number=2),
            PinView(name="PA3", port="A", number=3),
            PinView(name="PA5", port="A", number=5),
            PinView(name="PA6", port="A", number=6),
            PinView(name="PA7", port="A", number=7),
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
            PinView(name="PB6", port="B", number=6),
            PinView(name="PB7", port="B", number=7),
        ),
        connection_candidates=(
            ConnectionCandidateView(pin="PA9", peripheral="USART1", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA10", peripheral="USART1", signal="RX", af_number=1),
            ConnectionCandidateView(pin="PA2", peripheral="USART2", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA3", peripheral="USART2", signal="RX", af_number=1),
            ConnectionCandidateView(pin="PA5", peripheral="SPI1", signal="SCK", af_number=0),
            ConnectionCandidateView(pin="PA6", peripheral="SPI1", signal="MISO", af_number=0),
            ConnectionCandidateView(pin="PA7", peripheral="SPI1", signal="MOSI", af_number=0),
            ConnectionCandidateView(pin="PB7", peripheral="I2C1", signal="SDA", af_number=4),
            ConnectionCandidateView(pin="PB6", peripheral="I2C1", signal="SCL", af_number=4),
        ),
        dma_routes=(),
        clock_nodes=(
            ClockNodeView(node_id="HSI", parent=None, rate_hz=16_000_000, selector=None),
            ClockNodeView(node_id="HSE", parent=None, rate_hz=8_000_000, selector=None),
            ClockNodeView(node_id="PLL", parent="HSI", rate_hz=64_000_000, selector="PLL_M_N_R"),
            ClockNodeView(node_id="SYSCLK", parent="PLL", rate_hz=None, selector="MUX"),
            ClockNodeView(node_id="HCLK", parent="SYSCLK", rate_hz=None, selector="DIV"),
            ClockNodeView(node_id="APB1", parent="HCLK", rate_hz=None, selector="DIV"),
            ClockNodeView(node_id="APB2", parent="HCLK", rate_hz=None, selector="DIV"),
        ),
        payload={},
    )


# ---------------------------------------------------------------------------
# Project seeding
# ---------------------------------------------------------------------------


def seed_project(tmp_root: Path) -> ProjectConfig:
    """Build a fully-configured project + cached build metadata."""
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(
            name="blinky",
            alloy_cli="0.5.0",
            alloy="0.7.5",
            alloy_codegen="0.4.2",
            alloy_devices_yml="1.5.1",
        ),
        board=BoardRef(id="nucleo_g071rb"),
        chip=None,
        clocks={"profile": "pll_64mhz"},
        peripherals=(
            PeripheralEntry(
                kind="uart",
                name="console",
                payload={
                    "kind": "uart",
                    "name": "console",
                    "peripheral": "USART2",
                    "tx": "PA2",
                    "rx": "PA3",
                    "baud": 115200,
                },
            ),
            PeripheralEntry(
                kind="gpio",
                name="led",
                payload={
                    "kind": "gpio",
                    "name": "led",
                    "pin": "PA5",
                    "mode": "output",
                    "label": "ld4",
                    "initial": 0,
                },
            ),
            PeripheralEntry(
                kind="spi",
                name="flash",
                payload={
                    "kind": "spi",
                    "name": "flash",
                    "peripheral": "SPI1",
                    "sck": "PA5",
                    "miso": "PA6",
                    "mosi": "PA7",
                },
            ),
        ),
        build={"profile": "release", "optimization": "size", "lto": True},
        flash={"probe": "stlink"},
        raw={},
    )
    from alloy_cli.core import project as _project

    _project.write(tmp_root / "alloy.toml", config)

    cache = tmp_root / ".alloy" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "last_build.json").write_text(
        json.dumps(
            {
                "profile": "release",
                "ok": True,
                "elf": ".alloy/build/blinky.elf",
                "flash_bytes": 18432,
                "ram_bytes": 2048,
                "flash_capacity": 131072,
                "ram_capacity": 36864,
                "timestamp": "2026-05-02T18:00:00Z",
            }
        )
    )
    (cache / "events.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in (
                {"timestamp": "2026-05-02T17:55:00Z", "event": "alloy add gpio led"},
                {"timestamp": "2026-05-02T17:58:00Z", "event": "alloy build --profile release"},
                {"timestamp": "2026-05-02T18:00:00Z", "event": "alloy flash"},
            )
        )
    )
    return config


# ---------------------------------------------------------------------------
# Toolchain stubs
# ---------------------------------------------------------------------------


def stub_toolchains() -> None:
    """Pretend every toolchain is installed so the Dashboard pills all show."""
    from alloy_cli.core import toolchain
    from alloy_cli.core.toolchain import ToolchainStatus

    def _ok(name: str, version: str) -> ToolchainStatus:
        return ToolchainStatus(
            name=name, present=True, version=version, path=f"/opt/{name}", install_hint=None
        )

    toolchain.detect_arm_gcc = lambda: _ok("arm-none-eabi-gcc", "14.2.1")
    toolchain.detect_riscv_gcc = lambda: _ok("riscv64-unknown-elf-gcc", "14.2.0")
    toolchain.detect_xtensa_gcc = lambda: _ok("xtensa-esp32-elf-gcc", "13.2.0")
    toolchain.detect_probe_rs = lambda: _ok("probe-rs", "0.24.0")
    toolchain.detect_openocd = lambda: _ok("openocd", "0.12.0")
    toolchain.detect_cmake = lambda: _ok("cmake", "3.27.0")
    toolchain.detect_ninja = lambda: _ok("ninja", "1.11.1")

    # The dashboard now goes through `_toolchain.detect_*` so a
    # single rebind here propagates everywhere; no per-module
    # monkey-patching needed.


# ---------------------------------------------------------------------------
# App rendering
# ---------------------------------------------------------------------------


async def _render_async(
    app: TuiApp,
    *,
    title: str,
    settle: int = 4,
    size: tuple[int, int] = (120, 36),
) -> str:
    async with app.run_test(size=size) as pilot:
        for _ in range(settle):
            await pilot.pause()
        return app.export_screenshot(title=title)


def render_app(
    app: TuiApp,
    *,
    title: str,
    settle: int = 4,
    size: tuple[int, int] = (120, 36),
) -> str:
    """Render a Textual app to an SVG string.

    Wraps :meth:`TuiApp.export_screenshot` with a deterministic
    settle loop so the output is stable across runs.  Both the
    docs gallery script and the snapshot tests funnel through
    this single entry point.
    """
    return asyncio.run(_render_async(app, title=title, settle=settle, size=size))


def render_cli_snippet(name: str, argv: list[str], *, width: int = 120) -> str:
    """Render a CLI invocation through Rich into an SVG string.

    Used by the docs gallery for the help / boards / doctor
    snippets.  We isolate the render pipeline here so tests can
    exercise it without spawning a subprocess.
    """
    from click.testing import CliRunner

    from alloy_cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, argv, color=True)
    console = Console(record=True, width=width, file=io.StringIO())
    console.print(result.output, end="")
    return console.export_svg(title=f"alloy {' '.join(argv)}", clear=False)


# ---------------------------------------------------------------------------
# Pinned screens
# ---------------------------------------------------------------------------


def pinned_screen_names() -> tuple[str, ...]:
    """Stable sorted tuple of every pinned screen name (without extension)."""
    return (
        "01-welcome",
        "02-dashboard",
        "03-onboarding",
        "04-board-picker",
        "05-peripheral-add",
        "06-clock-tree",
        "07-dma-matrix",
        "08-memory-map",
    )


def build_app_for(name: str, *, project_root: Path) -> TuiApp:
    """Build the seeded ``TuiApp`` for one pinned screen name.

    Centralises the screen factory so the docs gallery + snapshot
    tests stay byte-stable.  ``project_root`` is the seeded
    directory holding ``alloy.toml`` + the board catalogue.
    """
    from alloy_cli.tui.screens.board_picker import BoardPickerScreen
    from alloy_cli.tui.screens.clock_tree import ClockTreeScreen
    from alloy_cli.tui.screens.dashboard import DashboardScreen
    from alloy_cli.tui.screens.dma_matrix import DmaMatrixScreen
    from alloy_cli.tui.screens.memory_map import MemoryMapScreen
    from alloy_cli.tui.screens.onboarding import OnboardingScreen
    from alloy_cli.tui.screens.peripheral_add import PeripheralAddScreen
    from alloy_cli.tui.screens.welcome import WelcomeScreen
    from alloy_cli.tui.widgets.dma_matrix import DmaMatrix, DmaMatrixCell
    from alloy_cli.tui.widgets.memory_map import MemoryMap, Section

    ir = make_ir()
    config = seed_project(project_root)

    if name == "01-welcome":
        return TuiApp(initial_screen=WelcomeScreen())
    if name == "02-dashboard":
        return TuiApp(initial_screen=DashboardScreen(project_dir=project_root))
    if name == "03-onboarding":
        return TuiApp(initial_screen=OnboardingScreen(root=project_root))
    if name == "04-board-picker":
        return TuiApp(initial_screen=BoardPickerScreen())
    if name == "05-peripheral-add":
        return TuiApp(
            initial_screen=PeripheralAddScreen(
                kind="uart",
                project_dir=project_root,
                config=config,
                device=ir,
            )
        )
    if name == "06-clock-tree":
        return TuiApp(
            initial_screen=ClockTreeScreen(
                ir=ir, config=config, device_max_hz=64_000_000
            )
        )
    if name == "07-dma-matrix":
        matrix = DmaMatrix.from_pairs(
            [
                DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH1", state="bound"),
                DmaMatrixCell(peripheral_signal="USART1_RX", channel="DMA1_CH2", state="bound"),
                DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH3", state="free"),
                DmaMatrixCell(peripheral_signal="SPI1_TX", channel="DMA1_CH3", state="free"),
                DmaMatrixCell(peripheral_signal="SPI1_RX", channel="DMA1_CH4", state="free"),
                DmaMatrixCell(
                    peripheral_signal="USART1_RX", channel="DMA1_CH4", state="conflict"
                ),
            ]
        )
        return TuiApp(initial_screen=DmaMatrixScreen(matrix=matrix))
    if name == "08-memory-map":
        memory = MemoryMap(
            flash_capacity=131072,
            ram_capacity=36864,
            sections=(
                Section(name=".text", region="flash", size_bytes=17920),
                Section(name=".rodata", region="flash", size_bytes=320),
                Section(name=".data", region="flash", size_bytes=192),
                Section(name=".bss", region="ram", size_bytes=2048),
            ),
        )
        return TuiApp(initial_screen=MemoryMapScreen(memory=memory))
    raise ValueError(f"Unknown pinned screen: {name!r}")


def prepare_snapshot_environment(tmp_root: Path) -> None:
    """Seed the catalog + project + stub toolchains for snapshot rendering."""
    seed_board_catalog(tmp_root)
    seed_project(tmp_root)
    stub_toolchains()


__all__ = [
    "build_app_for",
    "make_ir",
    "pinned_screen_names",
    "prepare_snapshot_environment",
    "render_app",
    "render_cli_snippet",
    "seed_board_catalog",
    "seed_project",
    "stub_toolchains",
]
