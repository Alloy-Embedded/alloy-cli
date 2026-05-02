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


__all__ = [
    "AlloyCliError",
    "BoardNotFoundError",
    "DataRepoMissingError",
    "DeviceNotFoundError",
    "DmaConflictError",
    "PinInvalidError",
    "ProjectConfigError",
    "ProjectConfigVersionError",
    "StaleDiffError",
    "ToolchainMissingError",
]
