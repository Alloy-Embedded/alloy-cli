"""Typed error hierarchy used by every façade.

Façades render these as exit codes (CLI), error toasts (TUI), or
structured MCP error payloads.  ``error_type`` strings are stable
contract — clients (especially LLMs via MCP) branch on them.
"""

from __future__ import annotations


class AlloyCliError(Exception):
    """Base class for every typed alloy-cli error."""

    error_type: str = "AlloyCliError"


class DeviceNotFoundError(AlloyCliError):
    error_type = "DeviceNotFoundError"


class BoardNotFoundError(AlloyCliError):
    error_type = "BoardNotFoundError"


class ProjectConfigError(AlloyCliError):
    error_type = "ProjectConfigError"


class ProjectConfigVersionError(ProjectConfigError):
    error_type = "ProjectConfigVersionError"


class PinInvalidError(AlloyCliError):
    error_type = "PinInvalidError"


class DmaConflictError(AlloyCliError):
    error_type = "DmaConflictError"


class ToolchainMissingError(AlloyCliError):
    error_type = "ToolchainMissingError"


class DataRepoMissingError(AlloyCliError):
    error_type = "DataRepoMissingError"


class StaleDiffError(AlloyCliError):
    error_type = "StaleDiffError"


class FamilyToolchainError(AlloyCliError):
    """Per-MCU-family toolchain manifest is missing, malformed, or
    references a parent that cannot be resolved.

    Sub-classes carry stable ``error_type`` strings (``family-toolchain-*``)
    that LLM agents and tests branch on without parsing messages.
    """

    error_type = "family-toolchain-error"


class FamilyToolchainCycleError(FamilyToolchainError):
    """The ``extends:`` chain forms a cycle (a → b → a)."""

    error_type = "family-toolchain-cycle"


class FamilyToolchainUnknownParentError(FamilyToolchainError):
    """A manifest declares ``extends: <id>`` but that family has no manifest."""

    error_type = "family-toolchain-unknown-parent"


class FamilyToolchainSchemaError(FamilyToolchainError):
    """Manifest YAML failed JSON Schema validation."""

    error_type = "family-toolchain-schema"


class FamilyToolchainNotFoundError(FamilyToolchainError):
    """No manifest ships under ``data/families/<family_id>.yml``."""

    error_type = "family-toolchain-not-found"


class FamilyToolchainInstallerError(AlloyCliError):
    """Base class for the binary installer (Wave 2 of toolchain-management).

    Sub-classes carry stable ``error_type`` strings
    (``family-toolchain-installer-*``) that LLM agents and tests
    branch on without parsing messages.
    """

    error_type = "family-toolchain-installer-error"


class FamilyToolchainInstallerChecksumError(FamilyToolchainInstallerError):
    """A downloaded artefact's SHA256 did not match the pinned value.

    Raised from the streaming download path BEFORE any byte is
    finalised on disk, so a tampered tarball never lands in the
    store.
    """

    error_type = "family-toolchain-installer-checksum"


class FamilyToolchainInstallerDownloadError(FamilyToolchainInstallerError):
    """The HTTP fetch failed (network, 4xx/5xx, redirect to non-pinned host)."""

    error_type = "family-toolchain-installer-download"


class FamilyToolchainInstallerExtractError(FamilyToolchainInstallerError):
    """Archive extraction failed (corrupt archive, unsupported member,
    path-traversal attempt)."""

    error_type = "family-toolchain-installer-extract"


class FamilyToolchainInstallerStoreCorruptError(FamilyToolchainInstallerError):
    """The toolchain store is in an inconsistent state.

    Surfaces when ``manifest.json`` references a SHA whose
    ``store/<sha>/`` directory is missing, or when an extraction
    directory exists without a manifest entry.
    """

    error_type = "family-toolchain-installer-store-corrupt"


class FamilyToolchainInstallerVersionMismatchError(FamilyToolchainInstallerError):
    """The project lockfile pins a version not present in the store.

    Raised by ``alloy build / flash / debug`` when the lockfile
    declares ``(tool, version, sha256)`` but the local store has
    a different (or no) extraction.
    """

    error_type = "family-toolchain-installer-version-mismatch"


class FamilyToolchainInstallerUnsupportedHostError(FamilyToolchainInstallerError):
    """The active host triple has no pin for the requested tool.

    Raised at adapter resolve time when ``platform.system()`` +
    ``platform.machine()`` produces a triple absent from the
    source pin file's ``hosts`` map.
    """

    error_type = "family-toolchain-installer-unsupported-host"


class FamilyToolchainInstallerLockedError(FamilyToolchainInstallerError):
    """Another alloy-cli process holds the toolchain store lock.

    The advisory file lock at ``<store>/.lock`` is held; the
    user should retry once the other invocation finishes.
    """

    error_type = "family-toolchain-installer-locked"


class OnboardingCancelledError(AlloyCliError):
    """User cancelled the onboarding wizard mid-flight.

    Raised by Wave-3 entry points (``alloy new`` interactive
    prompt, ``alloy setup``, the TUI ``OnboardingScreen``) when
    the user sends SIGINT or clicks Cancel.  The CLI maps this to
    exit code 130 (SIGINT convention).

    The exception carries the partial install outcomes via
    ``.partial_outcomes`` so callers can summarise "X of Y tools
    installed before you cancelled" without losing context.
    """

    error_type = "onboarding-cancelled"

    def __init__(
        self,
        message: str = "Onboarding cancelled by user.",
        *,
        partial_outcomes: tuple[object, ...] = (),
    ) -> None:
        super().__init__(message)
        # ``partial_outcomes`` is intentionally typed as ``object`` here
        # to avoid a circular import with
        # ``core.toolchain_orchestrator``.  Callers should treat it as
        # ``tuple[InstallOutcome, ...]``.
        self.partial_outcomes = partial_outcomes


# ---------------------------------------------------------------------------
# Wave 4 (recovery-tools): probe + erase error families
# ---------------------------------------------------------------------------


class FamilyToolchainProbeError(AlloyCliError):
    """Probe-side failure surfaced by ``core.probe_orchestrator``.

    Sub-classes carry stable ``family-toolchain-probe-*`` strings the
    CLI surfaces (`alloy reset`, `alloy erase`, `alloy monitor`) and
    the MCP probe tools branch on.  Keeping them under a shared base
    means consumers can ``except FamilyToolchainProbeError`` to catch
    the whole family without enumerating subclasses.
    """

    error_type = "family-toolchain-probe-error"


class FamilyToolchainProbeNotFoundError(FamilyToolchainProbeError):
    """The lockfile pins probe-rs / openocd but the binary is missing
    from the local store (e.g. after ``alloy toolchain prune``).

    Recovery: re-run ``alloy toolchain install`` to repopulate the
    store.
    """

    error_type = "family-toolchain-probe-not-found"


class FamilyToolchainProbeNotAttachedError(FamilyToolchainProbeError):
    """No probe is USB-attached.

    The orchestrator scanned the host with the lockfile-pinned
    probe-rs and got an empty list.  The CLI surfaces this as a clear
    "plug in your probe" message; the MCP tool returns it as a typed
    envelope with an empty ``detected_probes`` array.
    """

    error_type = "family-toolchain-probe-not-attached"


class FamilyToolchainProbeMultipleAttachedError(FamilyToolchainProbeError):
    """More than one probe is attached and ``--probe`` was not given.

    Carries ``.detected`` — a tuple of (vid, pid, serial, kind) tuples
    the CLI / MCP envelope renders so the user can pick one.
    """

    error_type = "family-toolchain-probe-multiple-attached"

    def __init__(
        self,
        message: str = "Multiple probes attached; pass --probe to disambiguate.",
        *,
        detected: tuple[tuple[str, str, str, str], ...] = (),
    ) -> None:
        super().__init__(message)
        self.detected = detected


class FamilyToolchainProbeUnauthorisedError(FamilyToolchainProbeError):
    """The detected probe is vendor-only (proprietary J-Link / locked
    ST-Link with vendor firmware) and cannot be auto-driven.

    Wave 4's contract: the orchestrator NEVER auto-invokes vendor
    tools.  The error message names the vendor utility the user must
    install.  ``.vendor_tool`` carries the human-readable name.
    """

    error_type = "family-toolchain-probe-unauthorised"

    def __init__(
        self,
        message: str = "Vendor-only probe detected; use the vendor tool manually.",
        *,
        vendor_tool: str = "",
        install_doc_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.vendor_tool = vendor_tool
        self.install_doc_url = install_doc_url


class FamilyToolchainEraseError(AlloyCliError):
    """Erase-side failure surfaced by ``core.probe_orchestrator``."""

    error_type = "family-toolchain-erase-error"


class FamilyToolchainEraseAbortedError(FamilyToolchainEraseError):
    """The user answered N at the confirmation prompt — or the CLI
    refused to proceed in a non-TTY without ``--auto`` / ``--yes``.
    """

    error_type = "family-toolchain-erase-aborted"


class FamilyToolchainEraseUnsupportedRegionError(FamilyToolchainEraseError):
    """``--region <name>`` does not resolve via the device IR's
    flash bank descriptors.

    ``.known_regions`` carries the regions the IR DOES expose so the
    error message can list them.
    """

    error_type = "family-toolchain-erase-unsupported-region"

    def __init__(
        self,
        message: str = "Unsupported erase region.",
        *,
        known_regions: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.known_regions = known_regions


class FamilyToolchainEraseConfirmationRequiredError(FamilyToolchainEraseError):
    """An MCP agent called ``probe_erase`` without ``confirm=true``.

    Mirrors Wave-3's two-phase pattern: the agent must call
    ``probe_erase_plan`` first, surface the plan to the user, get
    explicit confirmation, then call ``probe_erase`` with
    ``confirm=true``.
    """

    error_type = "family-toolchain-erase-confirmation-required"


class FamilyToolchainEraseProbeFailedError(FamilyToolchainEraseError):
    """The backend (probe-rs / openocd) returned non-zero during the
    erase.  ``.stderr`` carries the raw output for debugging.
    """

    error_type = "family-toolchain-erase-probe-failed"

    def __init__(
        self,
        message: str = "Probe-side erase failed.",
        *,
        stderr: str = "",
        returncode: int = -1,
    ) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class ProbeOperationCancelledError(AlloyCliError):
    """User pressed Ctrl+] in ``alloy monitor`` (graceful disconnect).

    Distinct from ``OnboardingCancelledError`` because it's a
    different user-flow event: not a wizard abort, just "I'm done
    looking at the log."  Carries the session summary
    (``duration_ms``, ``bytes_captured``, ``last_line``) so the CLI
    can render a one-line "Closed monitor session" summary.

    The CLI exits 0 on this error (graceful disconnect is not a
    failure).  Distinct exit code from ``OnboardingCancelledError``
    (130) — pinned in tests.
    """

    error_type = "probe-operation-cancelled"

    def __init__(
        self,
        message: str = "Probe operation cancelled by user.",
        *,
        duration_ms: int = 0,
        bytes_captured: int = 0,
        last_line: str | None = None,
    ) -> None:
        super().__init__(message)
        self.duration_ms = duration_ms
        self.bytes_captured = bytes_captured
        self.last_line = last_line


__all__ = [
    "AlloyCliError",
    "BoardNotFoundError",
    "DataRepoMissingError",
    "DeviceNotFoundError",
    "DmaConflictError",
    "FamilyToolchainCycleError",
    "FamilyToolchainEraseAbortedError",
    "FamilyToolchainEraseConfirmationRequiredError",
    "FamilyToolchainEraseError",
    "FamilyToolchainEraseProbeFailedError",
    "FamilyToolchainEraseUnsupportedRegionError",
    "FamilyToolchainError",
    "FamilyToolchainInstallerChecksumError",
    "FamilyToolchainInstallerDownloadError",
    "FamilyToolchainInstallerError",
    "FamilyToolchainInstallerExtractError",
    "FamilyToolchainInstallerLockedError",
    "FamilyToolchainInstallerStoreCorruptError",
    "FamilyToolchainInstallerUnsupportedHostError",
    "FamilyToolchainInstallerVersionMismatchError",
    "FamilyToolchainNotFoundError",
    "FamilyToolchainProbeError",
    "FamilyToolchainProbeMultipleAttachedError",
    "FamilyToolchainProbeNotAttachedError",
    "FamilyToolchainProbeNotFoundError",
    "FamilyToolchainProbeUnauthorisedError",
    "FamilyToolchainSchemaError",
    "FamilyToolchainUnknownParentError",
    "OnboardingCancelledError",
    "PinInvalidError",
    "ProbeOperationCancelledError",
    "ProjectConfigError",
    "ProjectConfigVersionError",
    "StaleDiffError",
    "ToolchainMissingError",
]
