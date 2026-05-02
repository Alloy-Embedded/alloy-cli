"""Host-toolchain detection.

Asks the OS where each known toolchain lives, returns version
strings, and gives per-OS install hints for missing ones.

Used by ``alloy build`` (Phase 2), ``alloy doctor`` (Phase 5),
the TUI dashboard (Phase 3) and the MCP server (Phase 4).
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolchainStatus:
    """Result of probing one toolchain on the host."""

    name: str
    present: bool
    version: str | None
    path: str | None
    install_hint: str | None


def _run_version(cmd: list[str], pattern: str) -> str | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
    except (FileNotFoundError, OSError):
        return None
    output = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(pattern, output)
    if match:
        return match.group(1) if match.groups() else match.group(0)
    return None


def _hints_for_arm_gcc() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install --cask gcc-arm-embedded"
    if system == "Linux":
        return "apt install gcc-arm-none-eabi   # or your distro equivalent"
    if system == "Windows":
        return "scoop install gcc-arm-none-eabi   # or via Arm Developer site"
    return "Install arm-none-eabi-gcc from https://developer.arm.com"


def _hints_for_riscv_gcc() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew tap riscv-software-src/riscv && brew install riscv-gnu-toolchain"
    if system == "Linux":
        return "apt install gcc-riscv64-unknown-elf   # or build from source"
    return (
        "Install riscv64-unknown-elf-gcc from https://github.com/riscv-collab/riscv-gnu-toolchain"
    )


def _hints_for_xtensa_gcc() -> str:
    return (
        "Install via espressif tooling: "
        "https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/index.html"
    )


def _hints_for_probe_rs() -> str:
    return "cargo install probe-rs --features cli   # or curl install script from probe.rs"


def _hints_for_openocd() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install openocd"
    if system == "Linux":
        return "apt install openocd"
    return "Install OpenOCD from https://openocd.org"


def detect_arm_gcc() -> ToolchainStatus:
    binary = "arm-none-eabi-gcc"
    path = shutil.which(binary)
    if path is None:
        return ToolchainStatus(
            name=binary,
            present=False,
            version=None,
            path=None,
            install_hint=_hints_for_arm_gcc(),
        )
    version = _run_version([binary, "--version"], r"\b(\d+\.\d+\.\d+)\b")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_riscv_gcc() -> ToolchainStatus:
    binary = "riscv64-unknown-elf-gcc"
    path = shutil.which(binary)
    if path is None:
        return ToolchainStatus(
            name=binary,
            present=False,
            version=None,
            path=None,
            install_hint=_hints_for_riscv_gcc(),
        )
    version = _run_version([binary, "--version"], r"\b(\d+\.\d+\.\d+)\b")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_xtensa_gcc() -> ToolchainStatus:
    binary = "xtensa-esp32-elf-gcc"
    path = shutil.which(binary)
    if path is None:
        return ToolchainStatus(
            name=binary,
            present=False,
            version=None,
            path=None,
            install_hint=_hints_for_xtensa_gcc(),
        )
    version = _run_version([binary, "--version"], r"\b(\d+\.\d+\.\d+)\b")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_probe_rs() -> ToolchainStatus:
    binary = "probe-rs"
    path = shutil.which(binary)
    if path is None:
        return ToolchainStatus(
            name=binary,
            present=False,
            version=None,
            path=None,
            install_hint=_hints_for_probe_rs(),
        )
    version = _run_version([binary, "--version"], r"probe-rs\s+(\S+)")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_openocd() -> ToolchainStatus:
    binary = "openocd"
    path = shutil.which(binary)
    if path is None:
        return ToolchainStatus(
            name=binary,
            present=False,
            version=None,
            path=None,
            install_hint=_hints_for_openocd(),
        )
    version = _run_version([binary, "--version"], r"Open On-Chip Debugger\s+(\S+)")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_cmake() -> ToolchainStatus:
    binary = "cmake"
    path = shutil.which(binary)
    if path is None:
        system = platform.system()
        hint = (
            "brew install cmake"
            if system == "Darwin"
            else "apt install cmake"
            if system == "Linux"
            else "scoop install cmake"
            if system == "Windows"
            else "https://cmake.org/download"
        )
        return ToolchainStatus(
            name=binary, present=False, version=None, path=None, install_hint=hint
        )
    version = _run_version([binary, "--version"], r"cmake version\s+(\S+)")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_ninja() -> ToolchainStatus:
    binary = "ninja"
    path = shutil.which(binary)
    if path is None:
        system = platform.system()
        hint = (
            "brew install ninja"
            if system == "Darwin"
            else "apt install ninja-build"
            if system == "Linux"
            else "scoop install ninja"
            if system == "Windows"
            else "https://github.com/ninja-build/ninja"
        )
        return ToolchainStatus(
            name=binary, present=False, version=None, path=None, install_hint=hint
        )
    version = _run_version([binary, "--version"], r"\b(\d+\.\d+\.\d+)\b")
    return ToolchainStatus(name=binary, present=True, version=version, path=path, install_hint=None)


def detect_all() -> dict[str, ToolchainStatus]:
    """Probe every known toolchain.  Used by ``alloy doctor``."""
    return {
        "arm-none-eabi-gcc": detect_arm_gcc(),
        "riscv64-unknown-elf-gcc": detect_riscv_gcc(),
        "xtensa-esp32-elf-gcc": detect_xtensa_gcc(),
        "probe-rs": detect_probe_rs(),
        "openocd": detect_openocd(),
        "cmake": detect_cmake(),
        "ninja": detect_ninja(),
    }


__all__ = [
    "ToolchainStatus",
    "detect_all",
    "detect_arm_gcc",
    "detect_cmake",
    "detect_ninja",
    "detect_openocd",
    "detect_probe_rs",
    "detect_riscv_gcc",
    "detect_xtensa_gcc",
]
