"""``ClockTreeWidget`` — text-rendered node-link view of the clock graph."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from alloy_cli.core.ir import ClockNodeView, DeviceIR


@dataclass(frozen=True, slots=True)
class ClockEdit:
    """One user-applied override on top of the IR's static rates."""

    node_id: str
    rate_hz: int


def compute_rates(
    ir: DeviceIR,
    *,
    overrides: Mapping[str, int] | None = None,
) -> dict[str, int | None]:
    """Best-effort upstream propagation of clock rates.

    Each node's rate is the max of (its own ``rate_hz``, the override
    table, the parent's resolved rate).  We treat unknown rates as
    ``None`` and skip them in the cascade so visualisations show
    "?".  The full per-PLL M/N/R algebra lives in alloy-codegen and
    feeds back here in a follow-up proposal.
    """
    overrides = overrides or {}
    by_id = {node.node_id: node for node in ir.clock_nodes}
    resolved: dict[str, int | None] = {nid: None for nid in by_id}

    def _resolve(node: ClockNodeView, depth: int = 0) -> int | None:
        if depth > 64:
            return None
        if resolved.get(node.node_id) is not None:
            return resolved[node.node_id]
        rate: int | None = node.rate_hz
        if node.node_id in overrides:
            rate = int(overrides[node.node_id])
        elif rate is None and node.parent and node.parent in by_id:
            rate = _resolve(by_id[node.parent], depth + 1)
        resolved[node.node_id] = rate
        return rate

    for node in ir.clock_nodes:
        _resolve(node)
    return resolved


def _format_rate(rate: int | None) -> str:
    if rate is None:
        return "?"
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.2f} MHz"
    if rate >= 1_000:
        return f"{rate / 1_000:.1f} kHz"
    return f"{rate} Hz"


class ClockTreeWidget(Widget):
    """Vertical-tree rendering of the clock graph.

    The widget is intentionally simple — every node renders on its
    own line with `name → rate` and a depth-based prefix.  The
    full graphical node-link layout lands as a polish follow-up.
    """

    DEFAULT_CSS: ClassVar[str] = """
    ClockTreeWidget {
        height: auto;
    }
    ClockTreeWidget .clock-line {
        height: 1;
    }
    ClockTreeWidget .clock-violation {
        color: $error;
        text-style: bold;
    }
    """

    def __init__(
        self,
        ir: DeviceIR,
        *,
        overrides: Mapping[str, int] | None = None,
        device_max_hz: int | None = None,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self._ir = ir
        self._overrides: dict[str, int] = dict(overrides or {})
        self._device_max_hz = device_max_hz

    @property
    def overrides(self) -> Mapping[str, int]:
        return self._overrides

    def set_override(self, node_id: str, rate_hz: int | None) -> None:
        if rate_hz is None:
            self._overrides.pop(node_id, None)
        else:
            self._overrides[node_id] = int(rate_hz)
        self.refresh(recompose=True)

    def compose(self) -> ComposeResult:
        rates = compute_rates(self._ir, overrides=self._overrides)
        with Vertical():
            if not self._ir.clock_nodes:
                yield Static("[dim]No clock graph in this device IR.[/dim]")
                return
            seen: set[str] = set()
            for root in _roots(self._ir.clock_nodes):
                yield from self._render_branch(root, rates, depth=0, seen=seen)

    def _render_branch(
        self,
        node: ClockNodeView,
        rates: dict[str, int | None],
        *,
        depth: int,
        seen: set[str],
    ) -> Iterable[Static]:
        if node.node_id in seen:
            return ()
        seen.add(node.node_id)
        prefix = "  " * depth + ("├─ " if depth else "")
        rate = rates.get(node.node_id)
        violates = (
            self._device_max_hz is not None and rate is not None and rate > self._device_max_hz
        )
        suffix = f" → {_format_rate(rate)}" + (
            f"  [error]exceeds {_format_rate(self._device_max_hz)}[/error]" if violates else ""
        )
        css = "clock-line clock-violation" if violates else "clock-line"
        yield Static(f"{prefix}{node.node_id}{suffix}", classes=css)
        for child in _children(self._ir.clock_nodes, node.node_id):
            yield from self._render_branch(child, rates, depth=depth + 1, seen=seen)


def _roots(nodes: Iterable[ClockNodeView]) -> tuple[ClockNodeView, ...]:
    by_id = {n.node_id: n for n in nodes}
    return tuple(n for n in nodes if not n.parent or n.parent not in by_id)


def _children(nodes: Iterable[ClockNodeView], parent_id: str) -> tuple[ClockNodeView, ...]:
    return tuple(n for n in nodes if n.parent == parent_id)


def violations(
    ir: DeviceIR, rates: Mapping[str, int | None], device_max_hz: int
) -> tuple[str, ...]:
    """Return node ids that exceed ``device_max_hz`` in ``rates``."""
    out = []
    for node in ir.clock_nodes:
        rate = rates.get(node.node_id)
        if rate is not None and rate > device_max_hz:
            out.append(node.node_id)
    return tuple(out)


__all__ = ["ClockEdit", "ClockTreeWidget", "compute_rates", "violations"]
