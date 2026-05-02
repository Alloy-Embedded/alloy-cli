"""Generate SVG documentation images for every TUI screen + key CLI commands.

Run from the repo root:

    python scripts/generate_docs_images.py

Outputs land in ``docs/images/``.  CI never runs this — it's a
developer-side helper that pins the visual state of the UI in
version-controlled SVGs.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

# Make src/ importable when running directly out of a checkout.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ruff: noqa: E402
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

OUT = _REPO_ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_board_catalog(tmp_root: Path) -> None:
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


def _make_ir() -> DeviceIR:
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
            PeripheralView(name="SPI1", ip_name="spi", ip_version="2.0", base_address=0x4001_3000),
            PeripheralView(name="I2C1", ip_name="i2c", ip_version="2.0", base_address=0x4000_5400),
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


def _seed_project(tmp_root: Path) -> ProjectConfig:
    """Build a fully-configured project with peripherals + cached build."""
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
# Screenshot routine
# ---------------------------------------------------------------------------


async def _shoot(
    name: str, app: TuiApp, *, settle: int = 4, size: tuple[int, int] = (120, 36)
) -> None:
    target = OUT / f"{name}.svg"
    async with app.run_test(size=size) as pilot:
        for _ in range(settle):
            await pilot.pause()
        svg = app.export_screenshot(title=f"alloy {name}")
    target.write_text(svg, encoding="utf-8")
    print(f"  ✓ {target.relative_to(_REPO_ROOT)}")


def _stub_toolchains() -> None:
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

    # Dashboard re-exports detect_* via `from alloy_cli.core.toolchain
    # import …` so we have to override the module-local bindings too.
    from alloy_cli.tui.screens import dashboard as _dashboard

    _dashboard.detect_arm_gcc = toolchain.detect_arm_gcc
    _dashboard.detect_cmake = toolchain.detect_cmake
    _dashboard.detect_probe_rs = toolchain.detect_probe_rs


async def shoot_all() -> None:
    project_root = _REPO_ROOT / ".tmp_screenshots"
    project_root.mkdir(parents=True, exist_ok=True)
    _seed_board_catalog(project_root)
    _seed_project(project_root)
    _stub_toolchains()
    ir = _make_ir()
    config = _seed_project(project_root)

    print("Generating SVG screenshots in", OUT)

    await _shoot("01-welcome", TuiApp(initial_screen=WelcomeScreen()))

    await _shoot(
        "02-dashboard",
        TuiApp(initial_screen=DashboardScreen(project_dir=project_root)),
    )

    await _shoot(
        "03-onboarding",
        TuiApp(initial_screen=OnboardingScreen(root=project_root)),
    )

    await _shoot(
        "04-board-picker",
        TuiApp(initial_screen=BoardPickerScreen()),
    )

    await _shoot(
        "05-peripheral-add",
        TuiApp(
            initial_screen=PeripheralAddScreen(
                kind="uart",
                project_dir=project_root,
                config=config,
                device=ir,
            )
        ),
    )

    await _shoot(
        "06-clock-tree",
        TuiApp(initial_screen=ClockTreeScreen(ir=ir, config=config, device_max_hz=64_000_000)),
    )

    matrix = DmaMatrix.from_pairs(
        [
            DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH1", state="bound"),
            DmaMatrixCell(peripheral_signal="USART1_RX", channel="DMA1_CH2", state="bound"),
            DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH3", state="free"),
            DmaMatrixCell(peripheral_signal="SPI1_TX", channel="DMA1_CH3", state="free"),
            DmaMatrixCell(peripheral_signal="SPI1_RX", channel="DMA1_CH4", state="free"),
            DmaMatrixCell(peripheral_signal="USART1_RX", channel="DMA1_CH4", state="conflict"),
        ]
    )
    await _shoot("07-dma-matrix", TuiApp(initial_screen=DmaMatrixScreen(matrix=matrix)))

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
    await _shoot("08-memory-map", TuiApp(initial_screen=MemoryMapScreen(memory=memory)))


# ---------------------------------------------------------------------------
# CLI snippets via Rich
# ---------------------------------------------------------------------------


def shoot_cli_snippets() -> None:
    """Render representative CLI outputs as SVGs via Rich."""
    from click.testing import CliRunner

    from alloy_cli.main import cli

    snippets = [
        ("09-cli-help", ["--help"]),
        ("10-cli-boards", ["boards"]),
        ("11-cli-doctor", ["doctor", "--project-dir", str(_REPO_ROOT / ".tmp_screenshots")]),
    ]
    runner = CliRunner()
    for name, argv in snippets:
        result = runner.invoke(cli, argv, color=True)
        # Re-render through Rich into SVG form so the output gets the
        # same chrome as the TUI screenshots.
        console = Console(record=True, width=120, file=io.StringIO())
        console.print(result.output, end="")
        target = OUT / f"{name}.svg"
        target.write_text(
            console.export_svg(title=f"alloy {' '.join(argv)}", clear=False),
            encoding="utf-8",
        )
        print(f"  ✓ {target.relative_to(_REPO_ROOT)} (rc={result.exit_code})")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    asyncio.run(shoot_all())
    shoot_cli_snippets()


if __name__ == "__main__":
    main()
