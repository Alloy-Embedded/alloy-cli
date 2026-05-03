"""Shared toolchain install walker — Wave 3 of toolchain-management.

The single seam every Wave-3 entry point ('alloy new' post-scaffold
prompt, 'alloy doctor --fix' toolchain auto-fixer, 'alloy setup',
the TUI OnboardingScreen, the MCP 'toolchain_apply_install_plan'
tool) routes through.  It walks a family manifest, dispatches every
non-vendor tool through the Wave-2 source adapter + manager pipeline,
and emits typed events callers translate into UI updates.

The module is intentionally **UI-free**: no ``input()``,
``Console``, ``Textual``, or ``sys.stdin`` reference.  Progress is
surfaced through a callback that receives frozen ``InstallEvent``
dataclasses; each entry point provides its own UI shell.

Vendor (EULA-gated) tools short-circuit: the walker emits
``ToolSkippedVendor`` with the per-OS install_doc URL and never
spawns a download.  Wave-2's contract is preserved.
"""

from __future__ import annotations

import platform
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alloy_cli.core import lockfile_toolchain as _lockfile
from alloy_cli.core import tool_sources as _ts
from alloy_cli.core import toolchain_manager as _tm
from alloy_cli.core.errors import (
    FamilyToolchainInstallerError,
    FamilyToolchainInstallerUnsupportedHostError,
)
from alloy_cli.core.project import AlloyDir
from alloy_cli.core.tool_sources import Downloader, HostTriple
from alloy_cli.core.toolchain_registry import (
    FamilyManifest,
    ToolRequirement,
)

# ---------------------------------------------------------------------------
# Event types (sealed union surfaced to the on_event callback)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolStarted:
    """Adapter resolved an artefact; the install is about to begin."""

    tool: str
    version: str
    source: str
    url: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ToolSkippedVendor:
    """Vendor (EULA-gated) tool — never auto-installed."""

    tool: str
    version: str
    install_doc_url: str | None


@dataclass(frozen=True, slots=True)
class ToolSkippedHostUnsupported:
    """The active host triple has no pin for this tool."""

    tool: str
    version: str
    host: str
    supported_hosts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolDownloaded:
    """Bytes finalised + SHA verified; extraction next."""

    tool: str
    version: str
    bytes_downloaded: int


@dataclass(frozen=True, slots=True)
class ToolInstalled:
    """Atomic promotion completed; lockfile pin staged for write."""

    tool: str
    version: str
    sha256: str
    store_path: Path
    bytes_downloaded: int
    udev_rules_path: Path | None
    skipped: bool  # True iff the manager treated this as a no-op


@dataclass(frozen=True, slots=True)
class ToolFailed:
    """One tool's install raised a typed error.

    The walker continues with the next tool — atomicity is per-tool;
    successive tools are independent.  Callers report the failure
    in the final summary.
    """

    tool: str
    version: str
    error_type: str
    message: str


InstallEvent = (
    ToolStarted
    | ToolSkippedVendor
    | ToolSkippedHostUnsupported
    | ToolDownloaded
    | ToolInstalled
    | ToolFailed
)


# ---------------------------------------------------------------------------
# Outcome + Report
# ---------------------------------------------------------------------------


# State strings — closed enum the typed report carries.  Adding a
# value is a Wave-4-or-later concern; UIs branch on this and want
# stability.
_STATE_INSTALLED = "installed"
_STATE_ALREADY_INSTALLED = "skipped-already-installed"
_STATE_VENDOR = "skipped-vendor"
_STATE_HOST_UNSUPPORTED = "skipped-host-unsupported"
_STATE_FAILED = "failed"

VALID_STATES: tuple[str, ...] = (
    _STATE_INSTALLED,
    _STATE_ALREADY_INSTALLED,
    _STATE_VENDOR,
    _STATE_HOST_UNSUPPORTED,
    _STATE_FAILED,
)


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    """One tool's final state after the walker visits it."""

    tool: str
    version: str
    state: str  # one of VALID_STATES
    sha256: str | None = None
    store_path: Path | None = None
    bytes_downloaded: int = 0
    install_doc_url: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    udev_rules_path: Path | None = None

    @property
    def installed(self) -> bool:
        """True iff this row counts as 'in the store and ready'."""
        return self.state in {_STATE_INSTALLED, _STATE_ALREADY_INSTALLED}

    @property
    def skipped(self) -> bool:
        """True iff the walker did not run the install (vendor / host / already)."""
        return self.state in {
            _STATE_VENDOR,
            _STATE_HOST_UNSUPPORTED,
            _STATE_ALREADY_INSTALLED,
        }


@dataclass(frozen=True, slots=True)
class InstallReport:
    """Result of one :func:`install_family` call."""

    family_id: str
    host: HostTriple
    outcomes: tuple[InstallOutcome, ...]
    total_bytes_downloaded: int
    lockfile_updated: bool
    lockfile_path: Path | None

    @property
    def installed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.installed)

    @property
    def failed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.state == _STATE_FAILED)

    @property
    def vendor_skipped(self) -> tuple[InstallOutcome, ...]:
        return tuple(o for o in self.outcomes if o.state == _STATE_VENDOR)


# ---------------------------------------------------------------------------
# Per-OS install_doc URL helper (shared with commands/toolchain.py)
# ---------------------------------------------------------------------------


_OS_DOC_KEYS: dict[str, str] = {
    "Darwin": "macos",
    "Linux": "linux",
    "Windows": "windows",
}


def _per_os_install_doc(install_docs: dict[str, str]) -> str | None:
    """Pick the OS-appropriate install doc URL for the active host."""
    if not install_docs:
        return None
    os_key = _OS_DOC_KEYS.get(platform.system())
    if os_key and os_key in install_docs:
        return install_docs[os_key]
    return next(iter(install_docs.values()), None)


def _supported_hosts_for_tool(tool_req: ToolRequirement) -> tuple[str, ...]:
    """Walk the pin file backing this tool and union every declared host.

    Used in :class:`ToolSkippedHostUnsupported` so UIs can suggest a
    different machine to retry from.
    """
    try:
        adapter = _ts.adapter_for(tool_req.source)
    except FamilyToolchainInstallerError:
        return ()
    try:
        payload: dict[str, Any] = _ts._load_pins(adapter.kind)
    except FamilyToolchainInstallerError:
        return ()
    seen: set[str] = set()
    for entry in payload.get("tools") or ():
        if not isinstance(entry, dict):
            continue
        if entry.get("tool") != tool_req.tool:
            continue
        hosts = entry.get("hosts") or {}
        seen.update(hosts.keys())
    return tuple(sorted(seen))


# ---------------------------------------------------------------------------
# Vendor short-circuit
# ---------------------------------------------------------------------------


def _emit(callback: Callable[[InstallEvent], None] | None, event: InstallEvent) -> None:
    if callback is not None:
        callback(event)


def _handle_vendor(
    tool_req: ToolRequirement,
    on_event: Callable[[InstallEvent], None] | None,
) -> InstallOutcome:
    doc_url = _per_os_install_doc(dict(tool_req.install_docs))
    _emit(
        on_event,
        ToolSkippedVendor(
            tool=tool_req.tool,
            version=tool_req.version,
            install_doc_url=doc_url,
        ),
    )
    return InstallOutcome(
        tool=tool_req.tool,
        version=tool_req.version,
        state=_STATE_VENDOR,
        install_doc_url=doc_url,
    )


def _handle_unsupported_host(
    tool_req: ToolRequirement,
    host: HostTriple,
    exc: FamilyToolchainInstallerUnsupportedHostError,
    on_event: Callable[[InstallEvent], None] | None,
) -> InstallOutcome:
    supported = _supported_hosts_for_tool(tool_req)
    _emit(
        on_event,
        ToolSkippedHostUnsupported(
            tool=tool_req.tool,
            version=tool_req.version,
            host=str(host),
            supported_hosts=supported,
        ),
    )
    return InstallOutcome(
        tool=tool_req.tool,
        version=tool_req.version,
        state=_STATE_HOST_UNSUPPORTED,
        error_type=getattr(exc, "error_type", "family-toolchain-installer-unsupported-host"),
        error_message=str(exc),
    )


def _handle_install_failure(
    tool_req: ToolRequirement,
    artifact_version: str,
    artifact_sha: str | None,
    exc: FamilyToolchainInstallerError,
    on_event: Callable[[InstallEvent], None] | None,
) -> InstallOutcome:
    err_type = getattr(exc, "error_type", "family-toolchain-installer-error")
    _emit(
        on_event,
        ToolFailed(
            tool=tool_req.tool,
            version=artifact_version or tool_req.version,
            error_type=err_type,
            message=str(exc),
        ),
    )
    return InstallOutcome(
        tool=tool_req.tool,
        version=artifact_version or tool_req.version,
        state=_STATE_FAILED,
        sha256=artifact_sha,
        error_type=err_type,
        error_message=str(exc),
    )


# ---------------------------------------------------------------------------
# Per-tool install
# ---------------------------------------------------------------------------


def _install_one(
    tool_req: ToolRequirement,
    host: HostTriple,
    *,
    force: bool,
    downloader: Downloader | None,
    on_event: Callable[[InstallEvent], None] | None,
) -> InstallOutcome:
    if tool_req.is_vendor:
        return _handle_vendor(tool_req, on_event)

    # Adapter resolve
    try:
        adapter = _ts.adapter_for(tool_req.source)
        artifact = adapter.resolve(tool_req, host)
    except FamilyToolchainInstallerUnsupportedHostError as exc:
        return _handle_unsupported_host(tool_req, host, exc, on_event)
    except FamilyToolchainInstallerError as exc:
        # Other resolve-time error (unknown source, bad pin file).
        return _handle_install_failure(tool_req, tool_req.version, None, exc, on_event)

    # Started
    _emit(
        on_event,
        ToolStarted(
            tool=tool_req.tool,
            version=artifact.version,
            source=artifact.source,
            url=artifact.url,
            size_bytes=artifact.size_bytes,
        ),
    )

    # Atomic install via Wave-2's manager
    try:
        result = _tm.install(
            artifact,
            force=force,
            downloader=downloader,
        )
    except FamilyToolchainInstallerError as exc:
        return _handle_install_failure(tool_req, artifact.version, artifact.sha256, exc, on_event)

    if not result.skipped and result.bytes_downloaded > 0:
        _emit(
            on_event,
            ToolDownloaded(
                tool=tool_req.tool,
                version=artifact.version,
                bytes_downloaded=result.bytes_downloaded,
            ),
        )

    _emit(
        on_event,
        ToolInstalled(
            tool=tool_req.tool,
            version=artifact.version,
            sha256=artifact.sha256,
            store_path=result.store_path,
            bytes_downloaded=result.bytes_downloaded,
            udev_rules_path=result.udev_rules_path,
            skipped=result.skipped,
        ),
    )

    state = _STATE_ALREADY_INSTALLED if result.skipped else _STATE_INSTALLED
    return InstallOutcome(
        tool=tool_req.tool,
        version=artifact.version,
        state=state,
        sha256=artifact.sha256,
        store_path=result.store_path,
        bytes_downloaded=result.bytes_downloaded,
        udev_rules_path=result.udev_rules_path,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_family(
    manifest: FamilyManifest,
    *,
    project_root: Path | None = None,
    include_optional: bool = False,
    force: bool = False,
    on_event: Callable[[InstallEvent], None] | None = None,
    downloader: Downloader | None = None,
) -> InstallReport:
    """Walk the family manifest and install every non-vendor tool.

    The single source of truth for "install the toolchain for this
    family."  Wave-3 entry points (``alloy new`` post-scaffold,
    ``alloy doctor --fix``, ``alloy setup``, the TUI Onboarding
    screen, the MCP ``toolchain_apply_install_plan``) all call this
    function.  No re-implementation of download / extract / SHA
    verify exists outside of Wave-2's manager + adapters.

    Parameters:
      manifest: the resolved family manifest (from
        :mod:`core.toolchain_registry`).
      project_root: when set, the project's
        ``.alloy/toolchain.lock`` is updated with every
        successfully-installed tool.  Pass ``None`` to skip the
        lockfile write (the ``--shared`` callsite).
      include_optional: when True, walks the optional tier too
        (default False — required + recommended only).
      force: when True, re-install every tool even when the SHA
        already matches the store entry.
      on_event: callback invoked once per state transition.  See
        :data:`InstallEvent` for the closed event union.  ``None``
        means "swallow events" — useful for tests that only check
        the report.
      downloader: override the module-level
        :data:`tool_sources.downloader` for this walk.  Tests pass
        a :class:`FakeDownloader` here.

    Returns:
      An :class:`InstallReport` with one :class:`InstallOutcome`
      per tool the walker visited (in tier order: required →
      recommended → optional when included).

    The function never raises ``FamilyToolchainInstaller*Error`` —
    those are caught and projected into ``ToolFailed`` events +
    ``state="failed"`` outcomes so a single bad pin doesn't take
    down the whole walk.  Lock-acquisition errors
    (``FamilyToolchainInstallerLockedError``) DO propagate because
    they affect the entire installer, not one tool.
    """
    host = _ts.host_triple()

    tiers: list[tuple[ToolRequirement, ...]] = [
        manifest.required,
        manifest.recommended,
    ]
    if include_optional:
        tiers.append(manifest.optional)

    # Lockfile setup (when project_root is provided)
    lock: _lockfile.ToolchainLock | None = None
    lock_path: Path | None = None
    if project_root is not None:
        lock_path = AlloyDir(root=project_root).base / _lockfile.LOCKFILE_NAME
        lock = _lockfile.read_optional(lock_path) or _lockfile.empty()

    outcomes: list[InstallOutcome] = []
    total_bytes = 0
    lock_changed = False

    for tier in tiers:
        for tool_req in tier:
            outcome = _install_one(
                tool_req,
                host,
                force=force,
                downloader=downloader,
                on_event=on_event,
            )
            outcomes.append(outcome)
            total_bytes += outcome.bytes_downloaded

            # Update the lockfile for installed (or already-installed)
            # tools — both states represent "this tool is in the store
            # at this (version, sha)" and the lockfile should reflect
            # that.  Failed / skipped-vendor / skipped-host-unsupported
            # do not touch the lockfile.
            if lock is not None and outcome.installed and outcome.sha256 is not None:
                new_lock = _lockfile.add(
                    lock,
                    outcome.tool,
                    outcome.version,
                    outcome.sha256,
                )
                if new_lock != lock:
                    lock = new_lock
                    lock_changed = True

    # Persist the lockfile once at the end so we don't pay N writes.
    lockfile_updated = False
    if lock is not None and lock_path is not None and lock_changed:
        _lockfile.write(lock_path, lock)
        lockfile_updated = True

    return InstallReport(
        family_id=manifest.family_id,
        host=host,
        outcomes=tuple(outcomes),
        total_bytes_downloaded=total_bytes,
        lockfile_updated=lockfile_updated,
        lockfile_path=lock_path if lockfile_updated else None,
    )


__all__ = [
    "VALID_STATES",
    "InstallEvent",
    "InstallOutcome",
    "InstallReport",
    "ToolDownloaded",
    "ToolFailed",
    "ToolInstalled",
    "ToolSkippedHostUnsupported",
    "ToolSkippedVendor",
    "ToolStarted",
    "install_family",
]
