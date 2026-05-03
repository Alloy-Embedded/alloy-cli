"""Shared probe orchestrator — Wave 4 of toolchain-management.

The single seam every Wave-4 entry point (``alloy reset``,
``alloy erase``, ``alloy monitor``, the TUI ``DebugScreen``
action group + ``MonitorScreen``, the four MCP probe tools)
routes through.  Owns probe selection, binary resolution from
``.alloy/toolchain.lock``, subprocess argv assembly, and the
typed-error vocabulary.

The module is intentionally **UI-free**: no ``input()``,
``Console``, ``Textual``, or ``sys.stdin`` reference.  Progress
is surfaced through callbacks that receive frozen
``MonitorEvent`` dataclasses (for streaming flows); each entry
point provides its own UI shell.

Vendor-only probes (proprietary J-Link, ST-Link with locked
firmware) raise ``FamilyToolchainProbeUnauthorisedError`` —
the orchestrator NEVER auto-invokes the vendor utility.

Wave-2's content-addressed store + lockfile own the binaries
this module dispatches.  The lockfile pin path resolves through
``toolchain_manager.resolve_for_lockfile`` so the orchestrator
inherits Wave-2's atomicity + sha-verification.
"""

from __future__ import annotations

import enum
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from alloy_cli.core import flash as _flash
from alloy_cli.core.errors import (
    FamilyToolchainEraseUnsupportedRegionError,
    FamilyToolchainProbeMultipleAttachedError,
    FamilyToolchainProbeNotAttachedError,
    FamilyToolchainProbeUnauthorisedError,
    ProbeOperationCancelledError,
)

# ---------------------------------------------------------------------------
# Frozen + slots dataclasses (typed events + reports + IDs)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProbeIdentity:
    """Identifier the orchestrator carries through every operation.

    ``vendor_only`` is True for proprietary J-Link / locked ST-Link
    devices alloy-cli cannot legally drive.  Selection raises
    :class:`FamilyToolchainProbeUnauthorisedError` for those probes.
    """

    vid: str  # 4-hex digits ("0483" for ST-Link)
    pid: str  # 4-hex digits ("374b" for ST-Link/V2-1)
    serial: str  # serial number string (may be empty for some probes)
    kind: str  # "stlink" | "jlink" | "cmsis-dap" | "picoprobe" | "esp-jtag" | …
    vendor_only: bool

    def selector(self) -> str:
        """Return the ``vid:pid:serial`` string the CLI uses."""
        return f"{self.vid}:{self.pid}:{self.serial}"


@dataclass(frozen=True, slots=True)
class ResetReport:
    """Result of a non-destructive reset."""

    probe: ProbeIdentity
    method: str  # "soft" | "hard"
    halt_after: bool
    duration_ms: int


@dataclass(frozen=True, slots=True)
class EraseRegion:
    """One flash region the user wants to erase.

    ``name`` is the user-facing label (``"all"``, ``"bootloader"``,
    or a literal range string for ``0xBASE-0xEND`` aliases).
    ``base`` + ``size`` are the resolved byte addresses.
    """

    name: str
    base: int
    size: int


@dataclass(frozen=True, slots=True)
class ErasePlan:
    """Preview of what an erase would touch — read-only."""

    probe: ProbeIdentity
    regions: tuple[EraseRegion, ...]
    total_bytes: int


@dataclass(frozen=True, slots=True)
class EraseReport:
    """Result of a destructive erase."""

    probe: ProbeIdentity
    regions: tuple[EraseRegion, ...]
    total_bytes_erased: int
    duration_ms: int


# Sealed union surfaced via the on_event callback in monitor sessions.


@dataclass(frozen=True, slots=True)
class MonitorOpened:
    """Session opened; bytes will start arriving."""

    probe: ProbeIdentity
    port: str  # serial path or "rtt://<channel>" for RTT mode
    baud: int
    mode: str  # "raw" | "rtt"
    started_at_ms: int


@dataclass(frozen=True, slots=True)
class MonitorBytes:
    """A chunk of bytes streamed from the target."""

    chunk: bytes
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class MonitorClosed:
    """Session closed (cleanly or via timeout)."""

    duration_ms: int
    bytes_captured: int
    last_line: str | None


MonitorEvent = MonitorOpened | MonitorBytes | MonitorClosed


# ---------------------------------------------------------------------------
# Reset method enum
# ---------------------------------------------------------------------------


class ResetMethod(str, enum.Enum):
    """Closed enum of reset methods callers may request."""

    SOFT = "soft"
    HARD = "hard"


# ---------------------------------------------------------------------------
# Probe Protocol + FakeProbe test seam
# ---------------------------------------------------------------------------


class Probe(Protocol):
    """Backend-agnostic probe handle."""

    @property
    def identity(self) -> ProbeIdentity: ...

    def reset(self, *, method: str, halt_after: bool) -> ResetReport: ...

    def erase(self, regions: Sequence[EraseRegion]) -> EraseReport: ...

    def monitor(
        self,
        *,
        port: Path | None,
        baud: int,
        mode: str,
        on_event: Callable[[MonitorEvent], None],
    ) -> int: ...


@dataclass(slots=True)
class _ResetCall:
    method: str
    halt_after: bool


@dataclass(slots=True)
class _EraseCall:
    regions: tuple[EraseRegion, ...]


@dataclass(slots=True)
class _MonitorCall:
    port: Path | None
    baud: int
    mode: str


class FakeProbe:
    """Test seam mirroring Wave 2's :class:`FakeDownloader` shape.

    Records every ``reset`` / ``erase`` / ``monitor`` call so tests
    can pin the dispatch contract.  Emits scripted ``MonitorEvent``s
    via :meth:`script_monitor_events`.  Tests can also inject typed
    failures via :meth:`fail_next_reset` / :meth:`fail_next_erase`.

    Not a Protocol implementer by virtue of structural typing — this
    class IS the Protocol surface and tests can use it interchangeably
    with the real backend.
    """

    def __init__(
        self,
        identity: ProbeIdentity | None = None,
        *,
        scripted_monitor_events: Iterable[MonitorEvent] | None = None,
    ) -> None:
        self._identity = identity or ProbeIdentity(
            vid="0483",
            pid="374b",
            serial="0671FF1234567890",
            kind="stlink",
            vendor_only=False,
        )
        self.reset_calls: list[_ResetCall] = []
        self.erase_calls: list[_EraseCall] = []
        self.monitor_calls: list[_MonitorCall] = []
        self._scripted_events: list[MonitorEvent] = list(scripted_monitor_events or [])
        self._next_reset_error: BaseException | None = None
        self._next_erase_error: BaseException | None = None

    # ---- Protocol surface ----

    @property
    def identity(self) -> ProbeIdentity:
        return self._identity

    def reset(self, *, method: str, halt_after: bool) -> ResetReport:
        self.reset_calls.append(_ResetCall(method=method, halt_after=halt_after))
        if self._next_reset_error is not None:
            err = self._next_reset_error
            self._next_reset_error = None
            raise err
        return ResetReport(
            probe=self._identity,
            method=method,
            halt_after=halt_after,
            duration_ms=12,
        )

    def erase(self, regions: Sequence[EraseRegion]) -> EraseReport:
        regions_tuple = tuple(regions)
        self.erase_calls.append(_EraseCall(regions=regions_tuple))
        if self._next_erase_error is not None:
            err = self._next_erase_error
            self._next_erase_error = None
            raise err
        total = sum(r.size for r in regions_tuple)
        return EraseReport(
            probe=self._identity,
            regions=regions_tuple,
            total_bytes_erased=total,
            duration_ms=200,
        )

    def monitor(
        self,
        *,
        port: Path | None,
        baud: int,
        mode: str,
        on_event: Callable[[MonitorEvent], None],
    ) -> int:
        self.monitor_calls.append(_MonitorCall(port=port, baud=baud, mode=mode))
        bytes_seen = 0
        for event in self._scripted_events:
            on_event(event)
            if isinstance(event, MonitorBytes):
                bytes_seen += len(event.chunk)
        return bytes_seen

    # ---- Test setters ----

    def script_monitor_events(self, events: Iterable[MonitorEvent]) -> None:
        self._scripted_events = list(events)

    def fail_next_reset(self, error: BaseException) -> None:
        self._next_reset_error = error

    def fail_next_erase(self, error: BaseException) -> None:
        self._next_erase_error = error


# ---------------------------------------------------------------------------
# Real probe-rs subprocess backend
# ---------------------------------------------------------------------------


class _RealProbeRsProbe:
    """Subprocess-backed :class:`Probe` implementation.

    Wraps the lockfile-pinned probe-rs binary.  Translates Wave-4's
    typed contract into the subprocess argv probe-rs expects + maps
    non-zero exit codes to typed errors.

    Tests that need a real backend can pass a ``runner`` argument
    (typically a :class:`FakeRunner`) so the subprocess seam is
    fully overridable.  Production callers leave it ``None`` and
    pick up :data:`alloy_cli.core.process.runner`.
    """

    def __init__(
        self,
        identity: ProbeIdentity,
        *,
        binary: str,
        runner: Any | None = None,
    ) -> None:
        self._identity = identity
        self._binary = binary
        # Late-import the runner to keep the module importable when
        # subprocess plumbing isn't ready (e.g. CI bootstrap).
        from alloy_cli.core import process as _process

        self._runner = runner if runner is not None else _process.runner

    @property
    def identity(self) -> ProbeIdentity:
        return self._identity

    def reset(self, *, method: str, halt_after: bool) -> ResetReport:
        argv = [self._binary, "reset"]
        if method == "hard":
            # probe-rs uses --connect-under-reset to drive nRST when
            # the probe + target support it.  Fall back to soft if
            # the backend doesn't recognise the flag (probe-rs <0.24
            # behaviour).
            argv.append("--connect-under-reset")
        if halt_after:
            argv.append("--halt-after-reset")
        argv.extend(self._probe_selector_argv())
        started = _now_ms()
        result = self._runner.run(argv)
        duration = _now_ms() - started
        if not result.ok:
            raise FamilyToolchainEraseProbeFailedError(
                f"probe-rs reset failed (returncode={result.returncode}): "
                f"{result.stderr or result.stdout}".strip(),
                stderr=result.stderr or result.stdout,
                returncode=result.returncode,
            )
        return ResetReport(
            probe=self._identity,
            method=method,
            halt_after=halt_after,
            duration_ms=duration,
        )

    def erase(self, regions: Sequence[EraseRegion]) -> EraseReport:
        # Wave-4: chip-wide erase only.  Per-region erase via
        # probe-rs requires `--restore-unwritten-bytes` + manual
        # offset/size flags; that lands in a follow-up.  For now,
        # if any region is anything other than "all", refuse with
        # a typed error so the CLI surfaces it cleanly.
        regions_tuple = tuple(regions)
        if not (len(regions_tuple) == 1 and regions_tuple[0].name == "all"):
            raise FamilyToolchainEraseProbeFailedError(
                "Per-region erase via probe-rs is not yet supported "
                "(Wave-4 ships chip-wide erase only).  Pass a chip-wide "
                "plan or use the vendor utility for partial erase.",
            )
        argv = [self._binary, "erase"]
        argv.extend(self._probe_selector_argv())
        started = _now_ms()
        result = self._runner.run(argv)
        duration = _now_ms() - started
        if not result.ok:
            raise FamilyToolchainEraseProbeFailedError(
                f"probe-rs erase failed (returncode={result.returncode}): "
                f"{result.stderr or result.stdout}".strip(),
                stderr=result.stderr or result.stdout,
                returncode=result.returncode,
            )
        return EraseReport(
            probe=self._identity,
            regions=regions_tuple,
            total_bytes_erased=regions_tuple[0].size,
            duration_ms=duration,
        )

    def monitor(
        self,
        *,
        port: Path | None,
        baud: int,
        mode: str,
        on_event: Callable[[MonitorEvent], None],
    ) -> int:
        # Wave-4 group 4 will wire this up to a real PySerial /
        # probe-rs RTT subprocess.  Group 2 only needs reset, so we
        # raise a typed error if a caller dispatches monitor through
        # the real backend before group 4 lands.
        raise NotImplementedError("Real-backend monitor is wired up in Wave-4 group 4.")

    def _probe_selector_argv(self) -> list[str]:
        """Build the ``--probe vid:pid:serial`` argv probe-rs expects."""
        if not self._identity.serial:
            return ["--probe", f"{self._identity.vid}:{self._identity.pid}"]
        return [
            "--probe",
            f"{self._identity.vid}:{self._identity.pid}:{self._identity.serial}",
        ]


def real_probe_for(
    identity: ProbeIdentity,
    *,
    project_root: Path | None = None,
    runner: Any | None = None,
) -> _RealProbeRsProbe:
    """Build a real backend probe for ``identity``.

    Resolves the probe-rs binary from the project lockfile (when set)
    so the orchestrator inherits Wave-2's atomicity + sha-verification.
    Tests pass an explicit ``runner`` to swap out the subprocess seam.
    """
    binary = _resolve_probe_rs_binary(project_root)
    return _RealProbeRsProbe(identity, binary=binary, runner=runner)


# Need to import the typed-failure error here so the real backend can
# raise it without a circular import.  Place the import at module
# bottom (post-class definition) once the file finishes loading.
from alloy_cli.core.errors import (  # noqa: E402
    FamilyToolchainEraseProbeFailedError,
)

# ---------------------------------------------------------------------------
# Probe selection
# ---------------------------------------------------------------------------


def _flash_probe_to_identity(info: _flash.ProbeInfo) -> ProbeIdentity:
    """Project a Wave-1 :class:`flash.ProbeInfo` to a Wave-4 identity.

    The ``vendor_only`` flag is computed from the probe kind:
    proprietary J-Link probes (`jlink`) carry vendor-locked firmware
    in many cases.  We mark them as vendor_only=True only when the
    probe's USB vid matches a known vendor-only signature.  Generic
    CMSIS-DAP / ST-Link / picoprobe probes are always non-vendor.

    For Wave 4 we keep the policy conservative: ONLY mark the probe
    as vendor-only when the user explicitly opted in via env override
    (``ALLOY_PROBE_VENDOR_ONLY=<vid:pid>``).  This avoids breaking
    the common-case "I bought a J-Link from SEGGER and it works
    fine" workflow.  Future waves can refine the heuristic.
    """
    import os

    override = os.environ.get("ALLOY_PROBE_VENDOR_ONLY", "")
    vendor_only = False
    if override:
        for pair in override.split(","):
            pair = pair.strip()
            if not pair:
                continue
            try:
                vid_s, pid_s = pair.split(":", 1)
            except ValueError:
                continue
            if (
                info.vendor_id is not None
                and info.product_id is not None
                and f"{info.vendor_id:04x}" == vid_s.lower()
                and f"{info.product_id:04x}" == pid_s.lower()
            ):
                vendor_only = True
                break

    vid = f"{info.vendor_id:04x}" if info.vendor_id is not None else "0000"
    pid = f"{info.product_id:04x}" if info.product_id is not None else "0000"
    return ProbeIdentity(
        vid=vid,
        pid=pid,
        serial=info.serial or "",
        kind=info.kind,
        vendor_only=vendor_only,
    )


def _resolve_probe_rs_binary(project_root: Path | None) -> str:
    """Resolve the probe-rs binary, preferring the project lockfile.

    Mirrors the helper in ``flash.run`` (Wave 2): when the project
    pins probe-rs, use the absolute path; otherwise fall back to
    ``"probe-rs"`` so the user's PATH wins (and a missing binary
    surfaces as ``family-toolchain-probe-not-found`` from the wrapper).
    """
    if project_root is None:
        return "probe-rs"
    from alloy_cli.core import toolchain_manager as _tm

    pinned = _tm.resolve_for_lockfile(project_root, "probe-rs")
    return str(pinned) if pinned is not None else "probe-rs"


def _list_probes(*, project_root: Path | None) -> tuple[ProbeIdentity, ...]:
    """Walk the host's USB bus via the lockfile-pinned probe-rs."""
    binary = _resolve_probe_rs_binary(project_root)
    try:
        infos = _flash.detect_probes(probe_rs_binary=binary)
    except Exception as exc:
        # Surface as not-found; the user probably doesn't have probe-rs
        # installed at all.
        raise FamilyToolchainProbeNotAttachedError(
            f"Could not enumerate probes via {binary!r}: {exc}",
        ) from exc
    return tuple(_flash_probe_to_identity(info) for info in infos)


def _match_hint(hint: str, probe: ProbeIdentity) -> bool:
    """Match ``hint`` against ``probe`` using the ``vid:pid:serial`` form.

    Each part is optional — ``"0483"`` matches every ST-Link;
    ``"0483:374b"`` matches every ST-Link/V2-1; the full triple
    pinpoints one probe.  Comparisons are case-insensitive.
    """
    hint = hint.strip().lower()
    if not hint:
        return False
    parts = hint.split(":")
    if len(parts) > 3:
        return False
    if parts[0] and parts[0] != probe.vid.lower():
        return False
    if len(parts) >= 2 and parts[1] and parts[1] != probe.pid.lower():
        return False
    if len(parts) == 3 and parts[2] and parts[2].lower() != probe.serial.lower():
        return False
    return True


def select_probe(
    *,
    hint: str | None = None,
    project_root: Path | None = None,
    probes: tuple[ProbeIdentity, ...] | None = None,
) -> ProbeIdentity:
    """Return the probe the orchestrator will dispatch against.

    Selection rules (matching ``alloy flash``'s semantics):

    - ``hint`` is None and one probe is attached → return it.
    - ``hint`` is None and zero probes are attached → raise
      ``FamilyToolchainProbeNotAttachedError``.
    - ``hint`` is None and N>1 probes are attached → raise
      ``FamilyToolchainProbeMultipleAttachedError`` with the list.
    - ``hint`` matches exactly one probe → return it.
    - ``hint`` matches zero probes → raise
      ``FamilyToolchainProbeNotAttachedError``.
    - ``hint`` matches multiple probes → raise
      ``FamilyToolchainProbeMultipleAttachedError`` with the matches.

    Vendor-only matches raise
    ``FamilyToolchainProbeUnauthorisedError`` so the orchestrator
    never returns a probe it cannot legally drive.

    The ``probes`` argument is a test seam — pass an explicit tuple
    to avoid the live host enumeration.
    """
    detected = probes if probes is not None else _list_probes(project_root=project_root)

    if hint:
        matches = tuple(p for p in detected if _match_hint(hint, p))
    else:
        matches = detected

    if not matches:
        raise FamilyToolchainProbeNotAttachedError(
            "No probe attached." + (f"  Hint {hint!r} matched nothing." if hint else ""),
        )
    if len(matches) > 1:
        raise FamilyToolchainProbeMultipleAttachedError(
            (f"{len(matches)} probes attached; pass --probe vid:pid:serial to disambiguate."),
            detected=tuple((p.vid, p.pid, p.serial, p.kind) for p in matches),
        )

    chosen = matches[0]
    if chosen.vendor_only:
        raise FamilyToolchainProbeUnauthorisedError(
            f"Probe {chosen.kind} {chosen.selector()} is vendor-only; install the "
            "vendor utility manually.",
            vendor_tool=_vendor_tool_for(chosen.kind),
        )
    return chosen


_VENDOR_TOOL_BY_KIND: dict[str, str] = {
    "jlink": "J-Link Commander",
    "stlink": "STM32CubeProgrammer",
}


def _vendor_tool_for(kind: str) -> str:
    return _VENDOR_TOOL_BY_KIND.get(kind, "the vendor utility")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def reset_target(
    probe: Probe,
    *,
    method: str = "soft",
    halt_after: bool = False,
) -> ResetReport:
    """Issue a non-destructive reset of the connected target.

    ``method`` is one of ``"soft"`` (default) / ``"hard"``.  Reset is
    idempotent + safe — no preview tool required.  Errors propagate
    typed: ``family-toolchain-probe-{not-attached, unauthorised}`` if
    the probe disappeared between selection and dispatch.
    """
    if method not in {"soft", "hard"}:
        raise ValueError(f"reset method must be 'soft' or 'hard'; got {method!r}")
    return probe.reset(method=method, halt_after=halt_after)


def plan_erase(
    probe: Probe,
    *,
    regions: Sequence[str] | None = None,
    project_root: Path | None = None,
    all_size_bytes: int | None = None,
    region_resolver: Callable[[str], EraseRegion] | None = None,
) -> ErasePlan:
    """Build an :class:`ErasePlan` without executing it.

    ``regions`` is a list of user-supplied tokens; each is either a
    region alias (resolved via ``region_resolver``) or a literal
    ``0xBASE-0xEND`` range.  ``None`` means "erase everything"
    (``all_size_bytes`` carries the chip-wide flash size in that
    case; if omitted, the plan reports ``size=0`` and the executor
    surfaces the size through the backend output).

    ``region_resolver`` is the device-IR-aware lookup function the
    caller provides — the orchestrator stays UI-free and chip-IR-
    agnostic.  When ``region_resolver`` is None, every alias raises
    ``FamilyToolchainEraseUnsupportedRegionError``.
    """
    del project_root  # reserved for future per-project resolution

    if regions is None:
        return ErasePlan(
            probe=probe.identity,
            regions=(EraseRegion(name="all", base=0, size=all_size_bytes or 0),),
            total_bytes=all_size_bytes or 0,
        )

    out: list[EraseRegion] = []
    for token in regions:
        token = token.strip()
        if not token:
            continue
        if "-" in token and token.lower().startswith("0x"):
            # Literal range token: 0xBASE-0xEND
            out.append(_parse_range_token(token))
            continue
        if region_resolver is None:
            raise FamilyToolchainEraseUnsupportedRegionError(
                f"Region alias {token!r} cannot be resolved (no region_resolver "
                "configured for this device)."
            )
        try:
            resolved = region_resolver(token)
        except KeyError as exc:
            raise FamilyToolchainEraseUnsupportedRegionError(
                f"Unknown region {token!r}.",
                known_regions=tuple(exc.args[0]) if exc.args else (),
            ) from exc
        out.append(resolved)

    total = sum(r.size for r in out)
    return ErasePlan(
        probe=probe.identity,
        regions=tuple(out),
        total_bytes=total,
    )


def _parse_range_token(token: str) -> EraseRegion:
    """Parse ``0xBASE-0xEND`` into an :class:`EraseRegion`."""
    base_s, _, end_s = token.partition("-")
    try:
        base = int(base_s, 16)
        end = int(end_s, 16)
    except ValueError as exc:
        raise FamilyToolchainEraseUnsupportedRegionError(
            f"Range {token!r} is not in 0xBASE-0xEND form."
        ) from exc
    if end <= base:
        raise FamilyToolchainEraseUnsupportedRegionError(
            f"Range {token!r}: end address must be greater than base."
        )
    return EraseRegion(name=token, base=base, size=end - base)


def execute_erase(probe: Probe, plan: ErasePlan) -> EraseReport:
    """Execute the erase plan.

    Per-tool failure is captured via the backend's exit code; the
    orchestrator wraps non-zero in
    :class:`FamilyToolchainEraseProbeFailedError` so callers can
    surface the typed envelope without parsing raw stderr.
    """
    return probe.erase(plan.regions)


def open_monitor(
    probe: Probe,
    *,
    port: Path | None = None,
    baud: int = 115200,
    mode: str = "raw",
    on_event: Callable[[MonitorEvent], None],
) -> int:
    """Open a streaming monitor session.

    Calls into the backend's ``monitor`` method, which pumps
    :class:`MonitorEvent`s back via the ``on_event`` callback.
    Returns the cumulative byte count once the session closes.

    Pressing Ctrl+] (in CLI / TUI) raises
    :class:`ProbeOperationCancelledError` from the backend; the
    caller catches it and renders the summary.

    ``mode`` is one of ``"raw"`` (UART) / ``"rtt"`` (probe-rs RTT
    channel).  Backend implementations dispatch accordingly.
    """
    if mode not in {"raw", "rtt"}:
        raise ValueError(f"monitor mode must be 'raw' or 'rtt'; got {mode!r}")
    return probe.monitor(port=port, baud=baud, mode=mode, on_event=on_event)


# ---------------------------------------------------------------------------
# MCP session table (Wave 4 group 6 will lean on this)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _MonitorSession:
    """In-memory monitor session keyed on a UUID for the MCP surface."""

    session_id: str
    probe: ProbeIdentity
    started_at_ms: int
    last_poll_ms: int
    buffer: list[bytes]
    bytes_total: int
    closed: bool
    last_line: str | None


class MonitorSessionTable:
    """Process-global table the MCP ``probe_monitor_*`` tools share.

    Sessions auto-close after ``idle_timeout_seconds`` of no ``poll``
    activity so a crashed agent does not leak threads forever.  The
    timeout is configurable so tests can pin shorter values.
    """

    def __init__(self, *, idle_timeout_seconds: float = 300.0) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self._sessions: dict[str, _MonitorSession] = {}

    def open(self, probe: ProbeIdentity) -> str:
        sid = uuid.uuid4().hex
        now = _now_ms()
        self._sessions[sid] = _MonitorSession(
            session_id=sid,
            probe=probe,
            started_at_ms=now,
            last_poll_ms=now,
            buffer=[],
            bytes_total=0,
            closed=False,
            last_line=None,
        )
        return sid

    def append_bytes(self, session_id: str, chunk: bytes) -> None:
        session = self._sessions.get(session_id)
        if session is None or session.closed:
            return
        session.buffer.append(chunk)
        session.bytes_total += len(chunk)
        # Track the last line for the close summary.
        if b"\n" in chunk:
            tail = chunk.rsplit(b"\n", 1)[0]
            decoded = tail.decode("utf-8", errors="replace").rsplit("\n", 1)[-1]
            session.last_line = decoded.strip() or session.last_line

    def poll(self, session_id: str) -> dict[str, Any]:
        session = self._require(session_id)
        self._maybe_timeout(session)
        if session.closed:
            raise ProbeOperationCancelledError(
                "Monitor session is closed.",
                duration_ms=_now_ms() - session.started_at_ms,
                bytes_captured=session.bytes_total,
                last_line=session.last_line,
            )
        new_bytes = b"".join(session.buffer)
        session.buffer.clear()
        session.last_poll_ms = _now_ms()
        return {
            "session_id": session_id,
            "new_bytes": new_bytes.decode("utf-8", errors="replace"),
            "total_bytes": session.bytes_total,
            "duration_ms": _now_ms() - session.started_at_ms,
            "closed": False,
        }

    def close(self, session_id: str) -> dict[str, Any]:
        session = self._require(session_id)
        if not session.closed:
            session.closed = True
        return {
            "session_id": session_id,
            "closed": True,
            "total_bytes": session.bytes_total,
            "duration_ms": _now_ms() - session.started_at_ms,
            "last_line": session.last_line,
        }

    def session(self, session_id: str) -> _MonitorSession:
        return self._require(session_id)

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if not s.closed)

    # ---- internals ----

    def _require(self, session_id: str) -> _MonitorSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ProbeOperationCancelledError(
                f"Unknown monitor session id {session_id!r}.",
            )
        return session

    def _maybe_timeout(self, session: _MonitorSession) -> None:
        if session.closed:
            return
        idle_ms = _now_ms() - session.last_poll_ms
        if idle_ms / 1000.0 > self.idle_timeout_seconds:
            session.closed = True


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    "ErasePlan",
    "EraseRegion",
    "EraseReport",
    "FakeProbe",
    "MonitorBytes",
    "MonitorClosed",
    "MonitorEvent",
    "MonitorOpened",
    "MonitorSessionTable",
    "Probe",
    "ProbeIdentity",
    "ResetMethod",
    "ResetReport",
    "execute_erase",
    "open_monitor",
    "plan_erase",
    "real_probe_for",
    "reset_target",
    "select_probe",
]


# Use ``Any`` import only for type hints in MonitorSessionTable.
_ = Any
