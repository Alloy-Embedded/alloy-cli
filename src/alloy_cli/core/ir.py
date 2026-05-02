"""IR loader over the ``alloy-devices-yml`` submodule.

Reads ``data/devices/vendors/<vendor>/<family>/devices/<device>.yml``
and exposes a typed view + query helpers.  The full Alloy canonical
IR has 60+ keys; we expose the subset the CLI / TUI / MCP need
without pulling in alloy-codegen as a runtime dependency.

The first parse of a YAML is cached on disk under
``.alloy/cache/ir/<v>_<f>_<d>.pkl`` keyed by file SHA + alloy-cli
version.  Cache hit < 10 ms.
"""

from __future__ import annotations

import hashlib
import pickle
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from alloy_cli import __version__
from alloy_cli.core.errors import DataRepoMissingError, DeviceNotFoundError

# ---------------------------------------------------------------------------
# Repository roots
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_DEVICES_ROOT = _REPO_ROOT / "data" / "devices"


def repo_root() -> Path:
    """Return the alloy-cli repo root."""
    return _REPO_ROOT


def data_devices_root() -> Path:
    """Return the path to the alloy-devices-yml submodule mount."""
    return _DATA_DEVICES_ROOT


def device_yaml_path(*, vendor: str, family: str, device: str) -> Path:
    """Return the canonical path of a device YAML.

    Does not check existence; pair with :func:`device_yaml_exists`.
    """
    return _DATA_DEVICES_ROOT / "vendors" / vendor / family / "devices" / f"{device}.yml"


def device_yaml_exists(*, vendor: str, family: str, device: str) -> bool:
    return device_yaml_path(vendor=vendor, family=family, device=device).exists()


# ---------------------------------------------------------------------------
# Typed views
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    vendor: str
    family: str
    device: str
    package: str
    core: str
    summary: str


@dataclass(frozen=True, slots=True)
class PeripheralView:
    """Minimal peripheral view used by the TUI / CLI / MCP."""

    name: str
    ip_name: str
    ip_version: str | None
    base_address: int


@dataclass(frozen=True, slots=True)
class PinView:
    name: str
    port: str | None
    number: int


@dataclass(frozen=True, slots=True)
class ConnectionCandidateView:
    """One ``(pin, signal)`` legal connection."""

    pin: str
    peripheral: str
    signal: str
    af_number: int | None


@dataclass(frozen=True, slots=True)
class DmaRouteView:
    controller: str
    peripheral: str
    direction: str  # "TX" | "RX" | "common"
    request_value: int | None


@dataclass(frozen=True, slots=True)
class ClockNodeView:
    node_id: str
    parent: str | None
    rate_hz: int | None
    selector: str | None


@dataclass(frozen=True, slots=True)
class DeviceIR:
    """Strongly-typed slice of the canonical IR.

    The raw payload is exposed as ``payload`` for advanced callers
    that need keys we haven't typed yet.
    """

    identity: DeviceIdentity
    peripherals: tuple[PeripheralView, ...]
    pins: tuple[PinView, ...]
    connection_candidates: tuple[ConnectionCandidateView, ...]
    dma_routes: tuple[DmaRouteView, ...]
    clock_nodes: tuple[ClockNodeView, ...]
    payload: dict[str, Any] = field(repr=False)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def discovered_device_registry() -> dict[tuple[str, str], tuple[str, ...]]:
    """Walk ``data/devices/vendors/`` and return
    ``(vendor, family) -> (device, ...)``.

    Raises :class:`DataRepoMissingError` if the submodule is not
    initialised.
    """
    vendors = _DATA_DEVICES_ROOT / "vendors"
    if not vendors.exists():
        raise DataRepoMissingError(
            "alloy-devices-yml submodule is not initialised — run "
            "`git submodule update --init` from the alloy-cli root."
        )
    registry: dict[tuple[str, str], list[str]] = {}
    for vendor_dir in sorted(vendors.iterdir()):
        if not vendor_dir.is_dir():
            continue
        for family_dir in sorted(vendor_dir.iterdir()):
            if not family_dir.is_dir():
                continue
            devices_dir = family_dir / "devices"
            if not devices_dir.exists():
                continue
            yamls = sorted(p.stem for p in devices_dir.glob("*.yml"))
            if yamls:
                registry[(vendor_dir.name, family_dir.name)] = yamls
    return {key: tuple(devices) for key, devices in registry.items()}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    cache_dir = _REPO_ROOT / ".alloy" / "cache" / "ir"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key(yaml_path: Path) -> str:
    """File SHA + alloy-cli version → cache key."""
    sha = hashlib.sha256(yaml_path.read_bytes()).hexdigest()[:16]
    return f"{sha}_{__version__}"


def _read_cached(yaml_path: Path, vendor: str, family: str, device: str) -> DeviceIR | None:
    cache_path = _cache_dir() / f"{vendor}_{family}_{device}.pkl"
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("rb") as fp:
            cached = pickle.load(fp)
    except (pickle.UnpicklingError, EOFError, AttributeError):
        return None
    if not isinstance(cached, dict) or cached.get("key") != _cache_key(yaml_path):
        return None
    return cached.get("ir")


def _write_cache(yaml_path: Path, vendor: str, family: str, device: str, ir: DeviceIR) -> None:
    cache_path = _cache_dir() / f"{vendor}_{family}_{device}.pkl"
    with cache_path.open("wb") as fp:
        pickle.dump({"key": _cache_key(yaml_path), "ir": ir}, fp)


# ---------------------------------------------------------------------------
# Loading + projection
# ---------------------------------------------------------------------------


def _project_ir(payload: dict[str, Any]) -> DeviceIR:
    identity_raw = payload.get("identity", {})
    identity = DeviceIdentity(
        vendor=str(identity_raw.get("vendor", "")),
        family=str(identity_raw.get("family", "")),
        device=str(identity_raw.get("device", "")),
        package=str(identity_raw.get("package", "")),
        core=str(identity_raw.get("core", "")),
        summary=str(identity_raw.get("summary", "")),
    )
    peripherals = tuple(
        PeripheralView(
            name=str(item.get("name", "")),
            ip_name=str(item.get("ip_name", "")),
            ip_version=item.get("ip_version"),
            base_address=int(item.get("base_address", 0)),
        )
        for item in payload.get("peripherals", []) or []
    )
    pins = tuple(
        PinView(
            name=str(item.get("name", "")),
            port=item.get("port"),
            number=int(item.get("number", 0)),
        )
        for item in payload.get("pins", []) or []
    )
    candidates = tuple(
        ConnectionCandidateView(
            pin=str(item.get("pin", "")),
            peripheral=str(item.get("peripheral", "")),
            signal=str(item.get("signal", "")),
            af_number=item.get("af_number"),
        )
        for item in payload.get("connection_candidates", []) or []
    )
    dma_routes = tuple(
        DmaRouteView(
            controller=str(item.get("controller", "")),
            peripheral=str(item.get("peripheral", "")),
            direction=str(item.get("direction", "common")),
            request_value=item.get("request_value"),
        )
        for item in payload.get("dma_routes", []) or []
    )
    clock_nodes = tuple(
        ClockNodeView(
            node_id=str(item.get("node_id", item.get("name", ""))),
            parent=item.get("parent"),
            rate_hz=item.get("rate_hz"),
            selector=item.get("selector"),
        )
        for item in payload.get("clock_nodes", []) or []
    )
    return DeviceIR(
        identity=identity,
        peripherals=peripherals,
        pins=pins,
        connection_candidates=candidates,
        dma_routes=dma_routes,
        clock_nodes=clock_nodes,
        payload=payload,
    )


def load_device(vendor: str, family: str, device: str) -> DeviceIR:
    """Load and project a device IR from the alloy-devices-yml submodule.

    Raises :class:`DeviceNotFoundError` when the YAML is missing.
    First load parses YAML; subsequent loads hit the on-disk cache.
    """
    yaml_path = device_yaml_path(vendor=vendor, family=family, device=device)
    if not yaml_path.exists():
        raise DeviceNotFoundError(
            f"Canonical device YAML not found: {yaml_path}.  "
            f"Run `alloy devices --search {device}` to find admitted alternatives."
        )
    cached = _read_cached(yaml_path, vendor, family, device)
    if cached is not None:
        return cached
    with yaml_path.open(encoding="utf-8") as fp:
        payload = yaml.safe_load(fp)
    if not isinstance(payload, dict):
        raise DeviceNotFoundError(
            f"Canonical YAML is malformed (expected mapping at root): {yaml_path}"
        )
    ir = _project_ir(payload)
    _write_cache(yaml_path, vendor, family, device, ir)
    return ir


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def connection_candidates(
    ir: DeviceIR, *, peripheral: str | None = None, signal: str | None = None
) -> tuple[ConnectionCandidateView, ...]:
    """Return candidate (pin, signal) connections, optionally filtered."""
    matches: list[ConnectionCandidateView] = []
    for cand in ir.connection_candidates:
        if peripheral is not None and cand.peripheral != peripheral:
            continue
        if signal is not None and cand.signal != signal:
            continue
        matches.append(cand)
    return tuple(matches)


def valid_pins_for(ir: DeviceIR, *, peripheral: str, signal: str) -> tuple[str, ...]:
    """Return pin names that legally drive ``peripheral.signal``."""
    return tuple(
        cand.pin for cand in connection_candidates(ir, peripheral=peripheral, signal=signal)
    )


def dma_routes(
    ir: DeviceIR, *, peripheral: str | None = None, direction: str | None = None
) -> tuple[DmaRouteView, ...]:
    """Return DMA routes matching the optional filters."""
    matches: list[DmaRouteView] = []
    for route in ir.dma_routes:
        if peripheral is not None and route.peripheral != peripheral:
            continue
        if direction is not None and route.direction != direction:
            continue
        matches.append(route)
    return tuple(matches)


def peripherals_with_class(ir: DeviceIR, ip_name: str) -> tuple[PeripheralView, ...]:
    """Return peripherals whose ``ip_name`` matches (e.g., ``"uart"``)."""
    return tuple(p for p in ir.peripherals if p.ip_name.lower() == ip_name.lower())


def peripheral_names(ir: DeviceIR) -> Sequence[str]:
    return tuple(p.name for p in ir.peripherals)


__all__ = [
    "ClockNodeView",
    "ConnectionCandidateView",
    "DeviceIR",
    "DeviceIdentity",
    "DmaRouteView",
    "PeripheralView",
    "PinView",
    "connection_candidates",
    "data_devices_root",
    "device_yaml_exists",
    "device_yaml_path",
    "discovered_device_registry",
    "dma_routes",
    "load_device",
    "peripheral_names",
    "peripherals_with_class",
    "repo_root",
    "valid_pins_for",
]
