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

    def get_tool(self, name: str) -> Tool:
        """Return the registered :class:`Tool` for ``name``.

        Raises :class:`ToolError(error_type="tool-not-found")`
        when the name isn't registered.  Tests + the stdio
        server both reach for this — accessing ``_tools``
        directly is no longer necessary.
        """
        if name not in self._tools:
            raise ToolError(error_type="tool-not-found", message=f"Unknown tool {name!r}.")
        return self._tools[name]

    def pop_tool(self, name: str) -> Tool | None:
        """Unregister + return the tool for ``name`` (or ``None``).

        Useful for tests that need to swap a tool with a stub
        and restore it afterwards.
        """
        return self._tools.pop(name, None)

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
    "timer": _peripherals.add_timer,
    "pwm": _peripherals.add_pwm,
    "adc": _peripherals.add_adc,
    "dac": _peripherals.add_dac,
    "can": _peripherals.add_can,
    "usb": _peripherals.add_usb,
    "eth": _peripherals.add_eth,
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


def _tool_add_timer(
    registry: ToolRegistry,
    *,
    name: str,
    period_ns: int,
    peripheral: str | None = None,
    divider: int | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Preview adding a timer peripheral.

    Preconditions: ``period_ns`` is required and must be positive.
    """
    payload: dict[str, Any] = {"period_ns": period_ns}
    if peripheral:
        payload["peripheral"] = peripheral
    if divider is not None:
        payload["divider"] = divider
    if mode is not None:
        payload["mode"] = mode
    return _store_and_summarise(
        registry, _preview(registry, kind="timer", name=name, payload=payload)
    )


def _tool_add_pwm(
    registry: ToolRegistry,
    *,
    name: str,
    channel: int,
    pin: str,
    peripheral: str | None = None,
    frequency_hz: int | None = None,
    duty_cycle: float | None = None,
) -> dict[str, Any]:
    """Preview adding a PWM channel; pin is validated against the IR."""
    payload: dict[str, Any] = {"channel": channel, "pin": pin}
    if peripheral:
        payload["peripheral"] = peripheral
    if frequency_hz is not None:
        payload["frequency_hz"] = frequency_hz
    if duty_cycle is not None:
        payload["duty_cycle"] = duty_cycle
    return _store_and_summarise(
        registry, _preview(registry, kind="pwm", name=name, payload=payload)
    )


def _tool_add_adc(
    registry: ToolRegistry,
    *,
    name: str,
    channels: list[dict[str, Any]],
    peripheral: str | None = None,
    resolution: int | None = None,
    dma: bool | None = None,
) -> dict[str, Any]:
    """Preview adding an ADC peripheral; channels are validated per-pin."""
    payload: dict[str, Any] = {"channels": channels}
    if peripheral:
        payload["peripheral"] = peripheral
    if resolution is not None:
        payload["resolution"] = resolution
    if dma is not None:
        payload["dma"] = dma
    return _store_and_summarise(
        registry, _preview(registry, kind="adc", name=name, payload=payload)
    )


def _tool_add_dac(
    registry: ToolRegistry,
    *,
    name: str,
    channel: int,
    pin: str,
    peripheral: str | None = None,
    output_buffer: bool | None = None,
) -> dict[str, Any]:
    """Preview adding a DAC channel."""
    payload: dict[str, Any] = {"channel": channel, "pin": pin}
    if peripheral:
        payload["peripheral"] = peripheral
    if output_buffer is not None:
        payload["output_buffer"] = output_buffer
    return _store_and_summarise(
        registry, _preview(registry, kind="dac", name=name, payload=payload)
    )


def _tool_add_can(
    registry: ToolRegistry,
    *,
    name: str,
    peripheral: str | None = None,
    tx: str | None = None,
    rx: str | None = None,
    bitrate: int | None = None,
    fd: bool | None = None,
) -> dict[str, Any]:
    """Preview adding a CAN bus peripheral."""
    payload: dict[str, Any] = {}
    if peripheral:
        payload["peripheral"] = peripheral
    if tx:
        payload["tx"] = tx
    if rx:
        payload["rx"] = rx
    if bitrate is not None:
        payload["bitrate"] = bitrate
    if fd is not None:
        payload["fd"] = fd
    return _store_and_summarise(
        registry, _preview(registry, kind="can", name=name, payload=payload)
    )


def _tool_add_usb(
    registry: ToolRegistry,
    *,
    name: str,
    mode: str,
    peripheral: str | None = None,
    speed: str | None = None,
) -> dict[str, Any]:
    """Preview adding a USB peripheral.  Mode must be one of: device, host, otg."""
    payload: dict[str, Any] = {"mode": mode}
    if peripheral:
        payload["peripheral"] = peripheral
    if speed:
        payload["speed"] = speed
    return _store_and_summarise(
        registry, _preview(registry, kind="usb", name=name, payload=payload)
    )


def _tool_add_eth(
    registry: ToolRegistry,
    *,
    name: str,
    interface: str,
    peripheral: str | None = None,
    phy_address: int | None = None,
) -> dict[str, Any]:
    """Preview adding an Ethernet peripheral.  Interface is one of: mii, rmii."""
    payload: dict[str, Any] = {"interface": interface}
    if peripheral:
        payload["peripheral"] = peripheral
    if phy_address is not None:
        payload["phy_address"] = phy_address
    return _store_and_summarise(
        registry, _preview(registry, kind="eth", name=name, payload=payload)
    )


def _tool_set_clock_profile(registry: ToolRegistry, *, profile: str) -> dict[str, Any]:
    """Switch the project's active clock profile (legacy).

    Lenient counterpart of ``activate_clock_profile``: writes
    ``[clocks].profile`` without checking whether the name exists in
    ``[clocks].profiles``.  Kept so existing 1.0.x flows keep working;
    new code should prefer ``activate_clock_profile`` (which fails
    fast on unknown names).
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
    from alloy_cli.core.project import dumps

    diff = UnifiedDiff(
        patches=(
            FilePatch(
                path=Path(PROJECT_FILE),
                before=dumps(config),
                after=dumps(new_config),
            ),
        )
    )
    diff_id = registry.diff_cache.store(diff, {"profile": profile})
    return {
        "diff_id": diff_id,
        "diff_text": diff.render(),
        "summary": {"clocks.profile": profile},
    }


def _tool_save_clock_profile(
    registry: ToolRegistry, *, name: str, rates: Mapping[str, int]
) -> dict[str, Any]:
    """Persist the in-screen clock overrides as a named profile.

    Preconditions: ``alloy.toml`` exists in the project dir.  Side
    effects: caches a UnifiedDiff under ``diff_id`` (apply with
    ``apply_diff``) — does not write the file directly.
    """
    from alloy_cli.core import clocks as _core_clocks

    config = _read_project(registry.project_dir)
    body = _core_clocks.profile_from_rates(rates)
    try:
        diff = _core_clocks.save_profile(config, name, body)
    except _core_clocks.InvalidProfileNameError as exc:
        raise ToolError(error_type="invalid-clock-profile-name", message=str(exc)) from exc
    diff_id = registry.diff_cache.store(diff, {"clocks.profiles": name})
    return {
        "diff_id": diff_id,
        "diff_text": diff.render(),
        "summary": {"clocks.profiles": name, "rates": dict(rates)},
    }


def _tool_activate_clock_profile(registry: ToolRegistry, *, name: str) -> dict[str, Any]:
    """Switch ``[clocks].profile`` to a profile that already exists.

    Preconditions: ``alloy.toml`` declares a profile named ``name``
    under ``[clocks].profiles``.  Side effects: caches a UnifiedDiff
    under ``diff_id``.  Use ``set_clock_profile`` for the legacy
    lenient variant that doesn't validate the reference.
    """
    from alloy_cli.core import clocks as _core_clocks

    config = _read_project(registry.project_dir)
    try:
        diff = _core_clocks.activate_profile(config, name)
    except _core_clocks.UnknownProfileError as exc:
        raise ToolError(error_type="unknown-clock-profile", message=str(exc)) from exc
    diff_id = registry.diff_cache.store(diff, {"clocks.profile": name})
    return {
        "diff_id": diff_id,
        "diff_text": diff.render(),
        "summary": {"clocks.profile": name},
    }


def _tool_build(registry: ToolRegistry, *, profile: str = "debug") -> dict[str, Any]:
    """Run cmake + ninja for the current project (no real toolchain check).

    Includes the alloy-codegen pre-step when alloy-codegen is
    importable; the result reports ``codegen_returncode`` so the
    LLM can branch on a codegen-only failure.
    """
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
        "codegen_returncode": result.codegen_returncode,
        "codegen_skipped": result.codegen_skipped,
        "codegen_reason": result.codegen_reason,
        "elf": str(result.elf_path) if result.elf_path else None,
    }


def _tool_regenerate(registry: ToolRegistry) -> dict[str, Any]:
    """Force a fresh alloy-codegen pass for the current project.

    Preconditions: alloy-codegen is importable in the active
    Python environment.  Side effects: writes one or more files
    under ``.alloy/generated/<device>/`` and updates the stamp
    file used by the build pipeline cache.
    """
    from alloy_cli.core import codegen as _codegen
    from alloy_cli.core.project import AlloyDir

    config = _read_project(registry.project_dir)
    layout = AlloyDir(root=registry.project_dir)
    layout.ensure()
    try:
        result = _codegen.force_regenerate(config, layout)
    except _codegen.CodegenError as exc:
        raise ToolError(error_type="codegen-not-installed", message=str(exc)) from exc
    return {
        "returncode": result.returncode,
        "skipped": result.skipped,
        "out_dir": str(result.out_dir),
        "written": [str(p.relative_to(registry.project_dir)) for p in result.written],
        "reason": result.reason,
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
    "add_timer": {
        "name": "string",
        "period_ns": "int",
        "peripheral": "string?",
        "divider": "int?",
        "mode": "string?",
    },
    "add_pwm": {
        "name": "string",
        "channel": "int",
        "pin": "string",
        "peripheral": "string?",
        "frequency_hz": "int?",
        "duty_cycle": "number?",
    },
    "add_adc": {
        "name": "string",
        "channels": "array<object>",
        "peripheral": "string?",
        "resolution": "int?",
        "dma": "bool?",
    },
    "add_dac": {
        "name": "string",
        "channel": "int",
        "pin": "string",
        "peripheral": "string?",
        "output_buffer": "bool?",
    },
    "add_can": {
        "name": "string",
        "peripheral": "string?",
        "tx": "string?",
        "rx": "string?",
        "bitrate": "int?",
        "fd": "bool?",
    },
    "add_usb": {
        "name": "string",
        "mode": "string",
        "peripheral": "string?",
        "speed": "string?",
    },
    "add_eth": {
        "name": "string",
        "interface": "string",
        "peripheral": "string?",
        "phy_address": "int?",
    },
    "set_clock_profile": {"profile": "string"},
    "save_clock_profile": {"name": "string", "rates": "object<string,int>"},
    "activate_clock_profile": {"name": "string"},
    "build": {"profile": "string"},
    "regenerate": {},
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
        "add_timer": _tool_add_timer,
        "add_pwm": _tool_add_pwm,
        "add_adc": _tool_add_adc,
        "add_dac": _tool_add_dac,
        "add_can": _tool_add_can,
        "add_usb": _tool_add_usb,
        "add_eth": _tool_add_eth,
        "set_clock_profile": _tool_set_clock_profile,
        "save_clock_profile": _tool_save_clock_profile,
        "activate_clock_profile": _tool_activate_clock_profile,
        "build": _tool_build,
        "regenerate": _tool_regenerate,
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
