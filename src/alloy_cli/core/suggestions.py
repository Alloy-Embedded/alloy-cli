"""Smart-default suggestions used by ``alloy add``.

Picks the lowest-numbered free IP instance + the first non-conflicting
candidate pin set + the lowest-numbered free DMA channel.  When the
caller supplies an explicit value, validators in :mod:`core.peripherals`
check it against the IR; the suggestions module is only consulted when
a flag is omitted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from alloy_cli.core import conflicts as _conflicts
from alloy_cli.core.ir import (
    ConnectionCandidateView,
    DeviceIR,
    connection_candidates,
    dma_routes,
    peripherals_with_class,
)
from alloy_cli.core.project import PeripheralEntry

_INSTANCE_TRAILING_NUMBER = re.compile(r"(\d+)$")


def _instance_sort_key(name: str) -> tuple[int, str]:
    match = _INSTANCE_TRAILING_NUMBER.search(name)
    return (int(match.group(1)) if match else 0, name)


def suggest_peripheral(
    ir: DeviceIR, *, ip_class: str, existing: Iterable[PeripheralEntry]
) -> str | None:
    """Pick the lowest-numbered free IP instance for ``ip_class``.

    ``ip_class`` matches :attr:`PeripheralView.ip_name` (e.g. ``"uart"``).
    """
    in_use = set(_conflicts.existing_peripheral_instances(existing).keys())
    candidates = sorted(
        peripherals_with_class(ir, ip_class),
        key=lambda p: _instance_sort_key(p.name),
    )
    for peripheral in candidates:
        if peripheral.name not in in_use:
            return peripheral.name
    return None


def suggest_pin(
    ir: DeviceIR,
    *,
    peripheral: str,
    signal: str,
    avoid_pins: set[str],
) -> str | None:
    """Pick the first IR-valid pin for ``peripheral.signal`` not in ``avoid_pins``."""
    for cand in connection_candidates(ir, peripheral=peripheral, signal=signal):
        if cand.pin not in avoid_pins:
            return cand.pin
    return None


def suggest_pin_set(
    ir: DeviceIR,
    *,
    peripheral: str,
    signals: tuple[str, ...],
    avoid_pins: set[str],
) -> dict[str, str] | None:
    """Pick a non-conflicting pin for each signal.

    Returns ``None`` if no consistent assignment exists.  Greedy
    allocation: scan each signal in order and consume an unused pin.
    """
    chosen: dict[str, str] = {}
    used: set[str] = set(avoid_pins)
    for signal in signals:
        pin = suggest_pin(ir, peripheral=peripheral, signal=signal, avoid_pins=used)
        if pin is None:
            return None
        chosen[signal] = pin
        used.add(pin)
    return chosen


def suggest_dma(
    ir: DeviceIR,
    *,
    peripheral: str,
    direction: str,  # "TX" | "RX" | "common"
    existing: Iterable[PeripheralEntry],
) -> str | None:
    """Lowest-numbered free DMA controller channel for ``peripheral`` + direction."""
    in_use = set(_conflicts.existing_dma_claims(existing).keys())
    routes = dma_routes(ir, peripheral=peripheral, direction=direction) or dma_routes(
        ir, peripheral=peripheral, direction="common"
    )
    sorted_routes = sorted(routes, key=lambda r: (r.controller, r.request_value or 0))
    for route in sorted_routes:
        chan = (
            f"{route.controller}#{route.request_value}"
            if route.request_value is not None
            else route.controller
        )
        if chan not in in_use:
            return chan
    return None


def candidate_pins(
    ir: DeviceIR, *, peripheral: str, signal: str
) -> tuple[ConnectionCandidateView, ...]:
    """Convenience wrapper returning the full candidate list (used in errors)."""
    return connection_candidates(ir, peripheral=peripheral, signal=signal)


__all__ = [
    "candidate_pins",
    "suggest_dma",
    "suggest_peripheral",
    "suggest_pin",
    "suggest_pin_set",
]
