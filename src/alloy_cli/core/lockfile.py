"""``.alloy/version.lock`` — exact pins of every Alloy ecosystem
component for reproducible builds.

Schema (TOML):

    schema_version = "1.0.0"

    [components]
    alloy             = "0.7.3"
    alloy-codegen     = "0.4.1"
    alloy-devices-yml = "1.5.0"
    alloy-cli         = "0.5.0"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from alloy_cli.core.errors import AlloyCliError

LOCKFILE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class AlloyLockfile:
    """Resolved versions of every Alloy ecosystem component."""

    schema_version: str
    alloy: str | None
    alloy_codegen: str | None
    alloy_devices_yml: str | None
    alloy_cli: str | None


def read_lock(path: Path) -> AlloyLockfile:
    if not path.exists():
        raise AlloyCliError(f"Lockfile not found: {path}")
    with path.open("rb") as fp:
        data = tomllib.load(fp)
    components = data.get("components") or {}
    return AlloyLockfile(
        schema_version=str(data.get("schema_version", LOCKFILE_SCHEMA_VERSION)),
        alloy=components.get("alloy"),
        alloy_codegen=components.get("alloy-codegen"),
        alloy_devices_yml=components.get("alloy-devices-yml"),
        alloy_cli=components.get("alloy-cli"),
    )


def write_lock(path: Path, lock: AlloyLockfile) -> None:
    """Serialise as deterministic TOML (no toml-write dep needed)."""
    lines = [
        f'schema_version = "{lock.schema_version}"',
        "",
        "[components]",
    ]
    if lock.alloy is not None:
        lines.append(f'alloy = "{lock.alloy}"')
    if lock.alloy_codegen is not None:
        lines.append(f'alloy-codegen = "{lock.alloy_codegen}"')
    if lock.alloy_devices_yml is not None:
        lines.append(f'alloy-devices-yml = "{lock.alloy_devices_yml}"')
    if lock.alloy_cli is not None:
        lines.append(f'alloy-cli = "{lock.alloy_cli}"')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


__all__ = ["LOCKFILE_SCHEMA_VERSION", "AlloyLockfile", "read_lock", "write_lock"]
