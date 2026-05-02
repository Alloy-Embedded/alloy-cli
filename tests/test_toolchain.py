"""Smoke tests for ``core.toolchain`` detection.

These tests are platform-aware — we don't *require* any toolchain
to be present, but we assert the result shape is consistent.
"""

from __future__ import annotations

from alloy_cli.core import toolchain


def test_detect_all_returns_known_keys() -> None:
    statuses = toolchain.detect_all()
    expected = {
        "arm-none-eabi-gcc",
        "riscv64-unknown-elf-gcc",
        "xtensa-esp32-elf-gcc",
        "probe-rs",
        "openocd",
        "cmake",
        "ninja",
    }
    assert set(statuses) == expected


def test_status_shape_consistent_for_missing_tool() -> None:
    status = toolchain.detect_xtensa_gcc()
    if status.present:
        assert status.path is not None
    else:
        assert status.path is None
        assert status.install_hint is not None


def test_detect_arm_gcc_status_shape() -> None:
    status = toolchain.detect_arm_gcc()
    assert status.name == "arm-none-eabi-gcc"
    assert isinstance(status.present, bool)
    if status.present:
        assert status.path is not None
    else:
        assert status.install_hint is not None
        assert "arm-none-eabi" in status.install_hint or "https://" in status.install_hint
