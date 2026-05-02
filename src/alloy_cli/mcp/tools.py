"""Transport-agnostic tool registry for the MCP server.

Every tool is a plain Python function that takes JSON-friendly
inputs (dicts / strings / ints) and returns a JSON-friendly result
(dict / list / scalar).  The MCP adapter in :mod:`server` wraps each
function with the SDK's tool-discovery + schema layer; tests call
the registry directly.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alloy_cli.core import boards as _boards
from alloy_cli.core import flash as _flash
from alloy_cli.core import ir as _ir
from alloy_cli.core import peripherals as _peripherals
from alloy_cli.core import process as _process
from alloy_cli.core import search as _search
from alloy_cli.core.diagnostics import UnifiedDiff
from alloy_cli.core.errors import (
    AlloyCliError,
    BoardNotFoundError,
    DeviceNotFoundError,
    PinInvalidError,
    StaleDiffError,
)
from alloy_cli.core.peripherals import AddArgs, AddResult
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig, read

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ToolError(Exception):
    """Structured error returned to LLM callers."""

    error_type: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover — repr-only path
        return f"{self.error_type}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            **self.detail,
        }


@dataclass(frozen=True, slots=True)
class Tool:
    """One tool surfaced to LLM clients."""

    name: str
    description: str
    handler: Callable[..., Any]
    parameter_schema: Mapping[str, Any]


@dataclass
class _CachedDiff:
    diff: UnifiedDiff
    proposed_summary: dict[str, Any]
    created_at: float


@dataclass
class DiffCache:
    """Two-phase ``preview → apply`` cache for mutating tools."""

    ttl_seconds: float = 300.0
    _entries: dict[str, _CachedDiff] = field(default_factory=dict)

    def store(self, diff: UnifiedDiff, proposed_summary: dict[str, Any]) -> str:
        diff_id = uuid.uuid4().hex
        self._entries[diff_id] = _CachedDiff(
            diff=diff, proposed_summary=proposed_summary, created_at=time.time()
        )
        return diff_id

    def fetch(self, diff_id: str) -> _CachedDiff:
        entry = self._entries.get(diff_id)
        if entry is None:
            raise ToolError(error_type="diff-not-found", message=f"Unknown diff_id {diff_id!r}.")
        if time.time() - entry.created_at > self.ttl_seconds:
            del self._entries[diff_id]
            raise StaleDiffError(
                f"diff_id {diff_id!r} has expired ({self.ttl_seconds:.0f}s window)."
            )
        return entry

    def discard(self, diff_id: str) -> None:
        self._entries.pop(diff_id, None)


@dataclass
class ToolRegistry:
    """Holds the canonical mapping from tool name to :class:`Tool`."""

    project_dir: Path
    runner: _process.CommandRunner
    diff_cache: DiffCache = field(default_factory=DiffCache)
    _tools: dict[str, Tool] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        if not tool.description.strip():
            raise ValueError(f"Tool {tool.name} must have a non-empty description.")
        self._tools[tool.name] = tool

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def call(self, tool_name: str, /, **kwargs: Any) -> Any:
        if tool_name not in self._tools:
            raise ToolError(error_type="tool-not-found", message=f"Unknown tool {tool_name!r}.")
        try:
            return self._tools[tool_name].handler(self, **kwargs)
        except ToolError:
            raise
        except (
            BoardNotFoundError,
            DeviceNotFoundError,
            PinInvalidError,
            AlloyCliError,
        ) as exc:
            raise ToolError(
                error_type=getattr(exc, "error_type", exc.__class__.__name__),
                message=str(exc),
            ) from exc


# ---------------------------------------------------------------------------
# Project + IR helpers
# ---------------------------------------------------------------------------


def _read_project(project_dir: Path) -> ProjectConfig:
    return read(project_dir / PROJECT_FILE)


def _resolve_device(config: ProjectConfig) -> _ir.DeviceIR:
    if config.chip is not None:
        return _ir.load_device(config.chip.vendor, config.chip.family, config.chip.device)
    if config.board is not None:
        manifest = _boards.lookup(config.board.id)
        return _ir.load_device(manifest.vendor, manifest.family, manifest.device)
    raise ToolError(
        error_type="missing-target",
        message="alloy.toml has neither [board] nor [chip].",
    )


def _board_summary_to_dict(b: _boards.BoardSummary) -> dict[str, Any]:
    return {
        "board_id": b.board_id,
        "mcu": b.mcu,
        "vendor": b.vendor,
        "family": b.family,
        "device": b.device,
        "core": b.core,
        "flash_size_bytes": b.flash_size_bytes,
        "tier": b.tier,
        "has_features": list(b.has_features),
        "clock_profiles": list(b.clock_profiles),
        "summary": b.summary,
    }


def _device_summary_to_dict(d: _search.DeviceSummary) -> dict[str, Any]:
    return {
        "vendor": d.vendor,
        "family": d.family,
        "device": d.device,
        "package": d.package,
        "core": d.core,
        "summary": d.summary,
        "admitted": d.admitted,
        "has_features": list(d.has_features),
    }


def _add_result_to_summary(result: AddResult) -> dict[str, Any]:
    return {
        "has_errors": result.has_errors,
        "diagnostics": [
            {
                "severity": d.severity,
                "code": d.code,
                "message": d.message,
                "path": d.path,
                "suggestions": list(d.suggestions),
            }
            for d in result.diagnostics
        ],
        "diff_text": result.diff.render(),
        "proposed": (
            {
                "kind": result.proposed.kind,
                "name": result.proposed.name,
                "payload": dict(result.proposed.payload),
            }
            if result.proposed
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _tool_list_boards(registry: ToolRegistry, *, query: str | None = None) -> list[dict[str, Any]]:
    """Return curated boards from the SDK catalogue.

    Preconditions: ``ALLOY_BOARDS_ROOT`` (or the equivalent SDK
    catalogue) is reachable.  Side effects: none.
    """
    results = _search.search_boards(query=query)
    return [_board_summary_to_dict(b) for b in results]


def _tool_list_devices(
    registry: ToolRegistry,
    *,
    query: str | None = None,
    vendor: str | None = None,
    family: str | None = None,
    include_bulk: bool = False,
) -> list[dict[str, Any]]:
    """Return device summaries from alloy-devices-yml.

    Preconditions: the alloy-devices-yml submodule is checked out.
    Side effects: none.
    """
    filters = _search.DeviceFilters(
        vendor=vendor, family=family, admitted="all" if include_bulk else "admitted"
    )
    return [
        _device_summary_to_dict(d) for d in _search.search_devices(query=query, filters=filters)
    ]


def _tool_query_device_ir(
    registry: ToolRegistry,
    *,
    vendor: str,
    family: str,
    device: str,
    peripheral_class: str | None = None,
) -> dict[str, Any]:
    """Return a narrow view of a device's IR.

    Preconditions: the device YAML exists in alloy-devices-yml.
    Side effects: none.
    """
    ir = _ir.load_device(vendor, family, device)
    peripherals = (
        _ir.peripherals_with_class(ir, peripheral_class) if peripheral_class else ir.peripherals
    )
    return {
        "identity": {
            "vendor": ir.identity.vendor,
            "family": ir.identity.family,
            "device": ir.identity.device,
            "package": ir.identity.package,
            "core": ir.identity.core,
            "summary": ir.identity.summary,
        },
        "peripherals": [
            {
                "name": p.name,
                "ip_name": p.ip_name,
                "ip_version": p.ip_version,
                "base_address": p.base_address,
            }
            for p in peripherals
        ],
        "pins": [{"name": p.name, "port": p.port, "number": p.number} for p in ir.pins],
    }


def _tool_suggest_pins(
    registry: ToolRegistry,
    *,
    vendor: str,
    family: str,
    device: str,
    peripheral: str,
    signal: str,
) -> list[str]:
    """Return IR-valid pin names for ``peripheral.signal`` on the device.

    Preconditions: the device IR exists.  Side effects: none.
    """
    ir = _ir.load_device(vendor, family, device)
    return list(_ir.valid_pins_for(ir, peripheral=peripheral, signal=signal))


def _tool_read_alloy_toml(registry: ToolRegistry) -> dict[str, Any]:
    """Return the parsed contents of ``alloy.toml`` in the current project.

    Preconditions: ``alloy.toml`` exists in ``project_dir``.
    Side effects: none.
    """
    config = _read_project(registry.project_dir)
    return {
        "schema_version": config.schema_version,
        "project": {
            "name": config.project.name,
            "alloy-cli": config.project.alloy_cli,
            "alloy": config.project.alloy,
            "alloy-codegen": config.project.alloy_codegen,
            "alloy-devices-yml": config.project.alloy_devices_yml,
        },
        "board": ({"id": config.board.id} if config.board else None),
        "chip": (
            {
                "vendor": config.chip.vendor,
                "family": config.chip.family,
                "device": config.chip.device,
            }
            if config.chip
            else None
        ),
        "clocks": dict(config.clocks),
        "peripherals": [
            {"kind": p.kind, "name": p.name, "payload": dict(p.payload)} for p in config.peripherals
        ],
        "build": dict(config.build),
        "flash": dict(config.flash),
    }


def _tool_list_recent_events(registry: ToolRegistry, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return the most recent entries from ``.alloy/cache/events.jsonl``.

    Preconditions: the project directory exists.  Side effects: none.
    """
    path = registry.project_dir / ".alloy" / "cache" / "events.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-int(limit) :]
    except OSError as exc:
        raise ToolError(error_type="io-error", message=str(exc)) from exc
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"raw": line})
    return out


# ----- mutating: preview / apply ------------------------------------------


_KIND_DISPATCH = {
    "uart": _peripherals.add_uart,
    "gpio": _peripherals.add_gpio,
    "spi": _peripherals.add_spi,
    "i2c": _peripherals.add_i2c,
}


def _preview(
    registry: ToolRegistry, *, kind: str, name: str, payload: Mapping[str, Any] | None = None
) -> AddResult:
    config = _read_project(registry.project_dir)
    device = _resolve_device(config)
    args = AddArgs.of(name, **dict(payload or {}))
    if kind in _KIND_DISPATCH:
        return _KIND_DISPATCH[kind](config, device, args)
    return _peripherals.add_generic(config, device, kind, args)


def _store_and_summarise(registry: ToolRegistry, result: AddResult) -> dict[str, Any]:
    summary = _add_result_to_summary(result)
    if result.has_errors or not result.diff.changed:
        return {**summary, "diff_id": None}
    diff_id = registry.diff_cache.store(result.diff, summary)
    return {**summary, "diff_id": diff_id}


def _tool_preview_diff(
    registry: ToolRegistry,
    *,
    kind: str,
    name: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a peripheral-add diff without writing files.

    Preconditions: ``alloy.toml`` exists and a target device IR is
    resolvable.  Side effects: caches the resulting diff under a
    ``diff_id`` for a 5-minute window.
    """
    return _store_and_summarise(registry, _preview(registry, kind=kind, name=name, payload=payload))


def _tool_apply_diff(registry: ToolRegistry, *, diff_id: str) -> dict[str, Any]:
    """Atomically write a previously-cached diff to disk.

    Preconditions: ``diff_id`` was returned by a recent
    ``preview_diff`` / ``add_*`` call.  Side effects: writes one or
    more files inside ``project_dir``.
    """
    cached = registry.diff_cache.fetch(diff_id)
    written: list[str] = []
    for patch in cached.diff.patches:
        if not patch.changed:
            continue
        target = registry.project_dir / patch.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch.after, encoding="utf-8")
        written.append(str(patch.path))
    registry.diff_cache.discard(diff_id)
    return {"applied": True, "written": written, "summary": cached.proposed_summary}


def _tool_add_uart(
    registry: ToolRegistry,
    *,
    name: str,
    peripheral: str | None = None,
    tx: str | None = None,
    rx: str | None = None,
    baud: int | None = None,
    dma: bool | None = None,
) -> dict[str, Any]:
    """Preview adding a UART peripheral to the project.

    Returns ``diff_id``; the LLM must call ``apply_diff(diff_id)``
    to land the change.  Preconditions: the device IR exposes the
    requested peripheral / signal.
    """
    payload: dict[str, Any] = {}
    if peripheral:
        payload["peripheral"] = peripheral
    if tx:
        payload["tx"] = tx
    if rx:
        payload["rx"] = rx
    if baud is not None:
        payload["baud"] = baud
    if dma is not None:
        payload["dma"] = dma
    return _store_and_summarise(
        registry, _preview(registry, kind="uart", name=name, payload=payload)
    )


def _tool_add_gpio(
    registry: ToolRegistry,
    *,
    name: str,
    pin: str,
    mode: str = "output",
    pull: str | None = None,
    initial: int | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Preview adding a GPIO peripheral to the project."""
    payload: dict[str, Any] = {"pin": pin, "mode": mode}
    if pull is not None:
        payload["pull"] = pull
    if initial is not None:
        payload["initial"] = initial
    if label is not None:
        payload["label"] = label
    return _store_and_summarise(
        registry, _preview(registry, kind="gpio", name=name, payload=payload)
    )


def _tool_add_spi(
    registry: ToolRegistry,
    *,
    name: str,
    peripheral: str | None = None,
    sck: str | None = None,
    miso: str | None = None,
    mosi: str | None = None,
) -> dict[str, Any]:
    """Preview adding an SPI peripheral to the project."""
    payload: dict[str, Any] = {}
    for key, value in (("peripheral", peripheral), ("sck", sck), ("miso", miso), ("mosi", mosi)):
        if value:
            payload[key] = value
    return _store_and_summarise(
        registry, _preview(registry, kind="spi", name=name, payload=payload)
    )


def _tool_add_i2c(
    registry: ToolRegistry,
    *,
    name: str,
    peripheral: str | None = None,
    sda: str | None = None,
    scl: str | None = None,
) -> dict[str, Any]:
    """Preview adding an I²C peripheral to the project."""
    payload: dict[str, Any] = {}
    for key, value in (("peripheral", peripheral), ("sda", sda), ("scl", scl)):
        if value:
            payload[key] = value
    return _store_and_summarise(
        registry, _preview(registry, kind="i2c", name=name, payload=payload)
    )


def _tool_set_clock_profile(registry: ToolRegistry, *, profile: str) -> dict[str, Any]:
    """Switch the project's active clock profile.

    Today this updates ``alloy.toml [clocks].profile``; downstream
    PLL algebra integration lands with the codegen runtime.
    """
    config = _read_project(registry.project_dir)
    new_clocks = dict(config.clocks)
    new_clocks["profile"] = profile
    new_config = ProjectConfig(
        schema_version=config.schema_version,
        project=config.project,
        board=config.board,
        chip=config.chip,
        clocks=new_clocks,
        peripherals=config.peripherals,
        build=config.build,
        flash=config.flash,
        raw=config.raw,
    )
    from alloy_cli.core.diagnostics import FilePatch
    from alloy_cli.core.peripherals import _emit_toml  # type: ignore[attr-defined]

    diff = UnifiedDiff(
        patches=(
            FilePatch(
                path=Path(PROJECT_FILE),
                before=_emit_toml(config),
                after=_emit_toml(new_config),
            ),
        )
    )
    diff_id = registry.diff_cache.store(diff, {"profile": profile})
    return {
        "diff_id": diff_id,
        "diff_text": diff.render(),
        "summary": {"clocks.profile": profile},
    }


def _tool_build(registry: ToolRegistry, *, profile: str = "debug") -> dict[str, Any]:
    """Run cmake + ninja for the current project (no real toolchain check)."""
    from alloy_cli.core import build as _build

    result = _build.run(
        project_root=registry.project_dir,
        profile=profile,  # type: ignore[arg-type]
        runner=registry.runner,
        require_toolchain=False,
    )
    return {
        "ok": result.ok,
        "profile": result.profile,
        "cmake_returncode": result.cmake_returncode,
        "build_returncode": result.build_returncode,
        "elf": str(result.elf_path) if result.elf_path else None,
    }


def _tool_flash(
    registry: ToolRegistry,
    *,
    elf: str,
    probe_kind: str = "auto",
    target: str | None = None,
) -> dict[str, Any]:
    """Flash a firmware ELF via probe-rs (no real toolchain check)."""
    config = _read_project(registry.project_dir)
    elf_path = registry.project_dir / elf
    result = _flash.run(
        elf=elf_path,
        config=config,
        probe_kind=probe_kind,
        target=target,
        runner=registry.runner,
        require_toolchain=False,
    )
    return {
        "ok": result.ok,
        "returncode": result.returncode,
        "probe": {
            "kind": result.probe.kind,
            "serial": result.probe.serial,
            "label": result.probe.label,
        },
    }


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------


_PARAM_SCHEMA: dict[str, dict[str, Any]] = {
    "list_boards": {"query": "string?"},
    "list_devices": {
        "query": "string?",
        "vendor": "string?",
        "family": "string?",
        "include_bulk": "bool",
    },
    "query_device_ir": {
        "vendor": "string",
        "family": "string",
        "device": "string",
        "peripheral_class": "string?",
    },
    "suggest_pins": {
        "vendor": "string",
        "family": "string",
        "device": "string",
        "peripheral": "string",
        "signal": "string",
    },
    "read_alloy_toml": {},
    "list_recent_events": {"limit": "int"},
    "preview_diff": {"kind": "string", "name": "string", "payload": "object?"},
    "apply_diff": {"diff_id": "string"},
    "add_uart": {
        "name": "string",
        "peripheral": "string?",
        "tx": "string?",
        "rx": "string?",
        "baud": "int?",
        "dma": "bool?",
    },
    "add_gpio": {
        "name": "string",
        "pin": "string",
        "mode": "string",
        "pull": "string?",
        "initial": "int?",
        "label": "string?",
    },
    "add_spi": {
        "name": "string",
        "peripheral": "string?",
        "sck": "string?",
        "miso": "string?",
        "mosi": "string?",
    },
    "add_i2c": {
        "name": "string",
        "peripheral": "string?",
        "sda": "string?",
        "scl": "string?",
    },
    "set_clock_profile": {"profile": "string"},
    "build": {"profile": "string"},
    "flash": {"elf": "string", "probe_kind": "string", "target": "string?"},
}


def build_default_registry(
    *,
    project_dir: Path | None = None,
    runner: _process.CommandRunner | None = None,
) -> ToolRegistry:
    """Construct the registry exposed by ``alloy mcp serve``."""
    registry = ToolRegistry(
        project_dir=(project_dir or Path.cwd()).resolve(),
        runner=runner or _process.runner,
    )
    handlers: dict[str, Callable[..., Any]] = {
        "list_boards": _tool_list_boards,
        "list_devices": _tool_list_devices,
        "query_device_ir": _tool_query_device_ir,
        "suggest_pins": _tool_suggest_pins,
        "read_alloy_toml": _tool_read_alloy_toml,
        "list_recent_events": _tool_list_recent_events,
        "preview_diff": _tool_preview_diff,
        "apply_diff": _tool_apply_diff,
        "add_uart": _tool_add_uart,
        "add_gpio": _tool_add_gpio,
        "add_spi": _tool_add_spi,
        "add_i2c": _tool_add_i2c,
        "set_clock_profile": _tool_set_clock_profile,
        "build": _tool_build,
        "flash": _tool_flash,
    }
    for name, handler in handlers.items():
        registry.register(
            Tool(
                name=name,
                description=(handler.__doc__ or "").strip(),
                handler=handler,
                parameter_schema=_PARAM_SCHEMA.get(name, {}),
            )
        )
    return registry


__all__ = [
    "DiffCache",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "build_default_registry",
]
