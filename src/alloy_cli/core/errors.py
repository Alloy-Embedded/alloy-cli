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


__all__ = [
    "AlloyCliError",
    "BoardNotFoundError",
    "DataRepoMissingError",
    "DeviceNotFoundError",
    "DmaConflictError",
    "FamilyToolchainCycleError",
    "FamilyToolchainError",
    "FamilyToolchainNotFoundError",
    "FamilyToolchainSchemaError",
    "FamilyToolchainUnknownParentError",
    "PinInvalidError",
    "ProjectConfigError",
    "ProjectConfigVersionError",
    "StaleDiffError",
    "ToolchainMissingError",
]
