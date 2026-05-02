"""Conflict detection across an in-flight ``ProjectConfig``.

Pin / DMA / peripheral-instance conflicts are caught before a diff
is even composed.  Used by :mod:`core.peripherals`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from alloy_cli.core.diagnostics import Diagnostic
from alloy_cli.core.project import PeripheralEntry, ProjectConfig


@dataclass(frozen=True, slots=True)
class PinClaim:
    """Who owns a pin in the current config."""

    holder: str  # peripheral name
    role: str  # "tx", "rx", "sda", "scl", "sck", "miso", "mosi", "cs", "pin", …


def _pin_keys() -> tuple[str, ...]:
    """All payload keys that name a pin we care about for conflicts."""
    return ("pin", "tx", "rx", "sda", "scl", "sck", "miso", "mosi", "cs")


def existing_pin_claims(peripherals: Iterable[PeripheralEntry]) -> dict[str, PinClaim]:
    """Map ``pin -> PinClaim`` over the existing peripheral list."""
    claims: dict[str, PinClaim] = {}
    for entry in peripherals:
        for key in _pin_keys():
            value = entry.payload.get(key)
            if isinstance(value, str) and value:
                # Don't override earlier claims (first one wins for diagnostics).
                claims.setdefault(value, PinClaim(holder=entry.name, role=key))
    return claims


def existing_peripheral_instances(peripherals: Iterable[PeripheralEntry]) -> dict[str, str]:
    """Map ``IP-instance (e.g. USART1) -> peripheral name`` already in use."""
    out: dict[str, str] = {}
    for entry in peripherals:
        instance = entry.payload.get("peripheral")
        if isinstance(instance, str) and instance:
            out.setdefault(instance, entry.name)
    return out


def existing_dma_claims(peripherals: Iterable[PeripheralEntry]) -> dict[str, str]:
    """Map ``DMA channel id -> peripheral name`` already in use."""
    out: dict[str, str] = {}
    for entry in peripherals:
        for key in ("dma", "tx_dma", "rx_dma"):
            value = entry.payload.get(key)
            if isinstance(value, str) and value:
                out.setdefault(value, entry.name)
    return out


def existing_names(peripherals: Iterable[PeripheralEntry]) -> set[str]:
    return {entry.name for entry in peripherals}


def detect(
    config: ProjectConfig, proposed: PeripheralEntry, *, exclude_self: bool = True
) -> tuple[Diagnostic, ...]:
    """Return diagnostics for any conflict between ``proposed`` and the existing config.

    ``exclude_self=True`` (default) skips the same-name entry when detecting
    pin / instance / DMA conflicts — so an in-place edit doesn't conflict
    with itself.  Name uniqueness is enforced unconditionally: duplicate
    names mean the user really did add twice.
    """
    others = [
        entry for entry in config.peripherals if not (exclude_self and entry.name == proposed.name)
    ]
    diagnostics: list[Diagnostic] = []

    # 1. Name uniqueness — always against the *full* list.
    if any(entry.name == proposed.name for entry in config.peripherals):
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="duplicate-name",
                message=f"Peripheral name {proposed.name!r} is already in use.",
                path=f"peripherals[{proposed.name}]",
            )
        )

    # 2. Peripheral instance conflict (USART1 used twice).
    proposed_instance = proposed.payload.get("peripheral")
    if isinstance(proposed_instance, str):
        existing = existing_peripheral_instances(others)
        if proposed_instance in existing:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="instance-in-use",
                    message=(
                        f"IP instance {proposed_instance} is already wired up by "
                        f"peripherals[{existing[proposed_instance]}]."
                    ),
                    path=f"peripherals[{proposed.name}].peripheral",
                )
            )

    # 3. Pin conflicts.
    existing_pins = existing_pin_claims(others)
    for key in _pin_keys():
        value = proposed.payload.get(key)
        if not isinstance(value, str):
            continue
        claim = existing_pins.get(value)
        if claim is None:
            continue
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="pin-in-use",
                message=(
                    f"Pin {value} is already used by peripherals[{claim.holder}]"
                    f" (role={claim.role})."
                ),
                path=f"peripherals[{proposed.name}].{key}",
            )
        )

    # 4. DMA channel conflicts.
    existing_dma = existing_dma_claims(others)
    for key in ("dma", "tx_dma", "rx_dma"):
        value = proposed.payload.get(key)
        if isinstance(value, str) and value in existing_dma:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="dma-in-use",
                    message=(
                        f"DMA channel {value} is already used by "
                        f"peripherals[{existing_dma[value]}]."
                    ),
                    path=f"peripherals[{proposed.name}].{key}",
                )
            )

    return tuple(diagnostics)


__all__ = [
    "PinClaim",
    "detect",
    "existing_dma_claims",
    "existing_names",
    "existing_peripheral_instances",
    "existing_pin_claims",
]
