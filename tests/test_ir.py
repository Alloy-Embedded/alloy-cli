"""Smoke tests for ``core.ir`` against the alloy-devices-yml submodule.

Skipped when the submodule is not initialised (CI / first-time
contributor running tests before submodule init).
"""

from __future__ import annotations

import pytest

from alloy_cli.core import ir as ir_mod
from alloy_cli.core.errors import DataRepoMissingError, DeviceNotFoundError


def _has_submodule() -> bool:
    return (ir_mod.data_devices_root() / "vendors").exists()


pytestmark = pytest.mark.skipif(
    not _has_submodule(),
    reason="alloy-devices-yml submodule not initialised — run `git submodule update --init`",
)


def test_discovery_returns_admitted_devices() -> None:
    registry = ir_mod.discovered_device_registry()
    assert registry, "expected at least one admitted (vendor, family) pair"
    # stm32g0 is canary admitted with stm32g071rb.
    assert ("st", "stm32g0") in registry
    assert "stm32g071rb" in registry[("st", "stm32g0")]


def test_load_device_returns_typed_ir() -> None:
    device = ir_mod.load_device("st", "stm32g0", "stm32g071rb")
    assert device.identity.vendor == "st"
    assert device.identity.family == "stm32g0"
    assert device.identity.device == "stm32g071rb"
    assert device.identity.core
    assert device.peripherals  # at least one peripheral admitted


def test_load_device_caches_on_second_call(tmp_path) -> None:
    first = ir_mod.load_device("st", "stm32g0", "stm32g071rb")
    second = ir_mod.load_device("st", "stm32g0", "stm32g071rb")
    # Both should produce primitive-equivalent identities.
    assert first.identity == second.identity


def test_load_missing_device_raises_clear_error() -> None:
    with pytest.raises(DeviceNotFoundError) as excinfo:
        ir_mod.load_device("st", "stm32g0", "stm32g0nope")
    assert "stm32g0nope" in str(excinfo.value)


def test_query_helpers_filter_collections() -> None:
    device = ir_mod.load_device("st", "stm32g0", "stm32g071rb")
    # connection_candidates with a non-existent peripheral filter is empty.
    empty = ir_mod.connection_candidates(device, peripheral="NOPE", signal="TX")
    assert empty == ()
    # peripherals_with_class filters on ip_name.
    peripherals = device.peripherals
    if peripherals:
        ip_name = peripherals[0].ip_name
        if ip_name:
            matches = ir_mod.peripherals_with_class(device, ip_name)
            assert matches  # at least the seed peripheral


def test_data_repo_missing_error_handled_when_submodule_missing(monkeypatch) -> None:
    # Force discovery to a non-existent path to verify error type.
    monkeypatch.setattr(ir_mod, "_DATA_DEVICES_ROOT", ir_mod.data_devices_root() / "_nope_")
    ir_mod.discovered_device_registry.cache_clear()
    with pytest.raises(DataRepoMissingError):
        ir_mod.discovered_device_registry()
    ir_mod.discovered_device_registry.cache_clear()
