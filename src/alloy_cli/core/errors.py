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


__all__ = [
    "AlloyCliError",
    "BoardNotFoundError",
    "DataRepoMissingError",
    "DeviceNotFoundError",
    "DmaConflictError",
    "FamilyToolchainCycleError",
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
    "FamilyToolchainSchemaError",
    "FamilyToolchainUnknownParentError",
    "PinInvalidError",
    "ProjectConfigError",
    "ProjectConfigVersionError",
    "StaleDiffError",
    "ToolchainMissingError",
]
