"""Reader / writer for ``.alloy/toolchain.lock``.

The toolchain lockfile pins the exact ``(version, sha256)`` per tool
this project consumes.  It is separate from
``.alloy/version.lock`` (which pins alloy / alloy-codegen /
alloy-devices-yml) because the two have different cadences — a
project can hop arm-gcc 14.2 → 14.3 without touching any alloy
ecosystem component, and vice-versa.

On-disk format (TOML):

    schema_version = "1.0.0"

    [tools]
    "arm-none-eabi-gcc" = { version = "14.2.1-1.1", sha256 = "abc..." }
    "probe-rs"          = { version = "0.27.0", sha256 = "def..." }

The single canonical emitter :func:`dumps` is the only function
that produces TOML text, so two callers can never drift.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from alloy_cli.core.errors import ProjectConfigError

LOCKFILE_NAME = "toolchain.lock"
SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Typed views
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolchainPin:
    """One ``[tools].<name>`` entry."""

    version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ToolchainLock:
    """Decoded ``.alloy/toolchain.lock`` body.

    ``tools`` maps the tool name to its pin; iteration order is
    alphabetical so :func:`dumps` is byte-stable.
    """

    schema_version: str = SCHEMA_VERSION
    tools: Mapping[str, ToolchainPin] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolchainLockChange:
    """One entry in :func:`diff` output."""

    tool: str
    kind: str  # "added" | "removed" | "version-changed" | "sha-changed"
    before: ToolchainPin | None
    after: ToolchainPin | None


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _check_schema_version(text_version: str) -> None:
    parts = text_version.split(".")
    if len(parts) != 3 or not parts[0].isdigit():
        raise ProjectConfigError(
            f"toolchain.lock schema_version {text_version!r} is not a "
            "3-segment SemVer string."
        )
    major = int(parts[0])
    if major != 1:
        raise ProjectConfigError(
            f"toolchain.lock declares schema_version {text_version!r} "
            f"(major={major}); this alloy-cli understands major=1."
        )


def _decode_tools(raw: object, *, source: str) -> dict[str, ToolchainPin]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ProjectConfigError(
            f"{source}: [tools] must be a table, got {type(raw).__name__}."
        )
    out: dict[str, ToolchainPin] = {}
    for name, body in raw.items():
        if not isinstance(name, str) or not name:
            raise ProjectConfigError(
                f"{source}: [tools] entry has invalid name {name!r}."
            )
        if not isinstance(body, dict):
            raise ProjectConfigError(
                f"{source}: [tools].{name} must be an inline table."
            )
        version = body.get("version")
        sha256 = body.get("sha256")
        if not isinstance(version, str) or not version:
            raise ProjectConfigError(
                f"{source}: [tools].{name} is missing a non-empty `version`."
            )
        if not isinstance(sha256, str) or not sha256:
            raise ProjectConfigError(
                f"{source}: [tools].{name} is missing a non-empty `sha256`."
            )
        out[name] = ToolchainPin(version=version, sha256=sha256)
    return out


def parse(payload: dict[str, object], *, source: str = "toolchain.lock") -> ToolchainLock:
    """Validate + decode an already-parsed TOML payload."""
    schema_version = payload.get("schema_version", "")
    if not isinstance(schema_version, str) or not schema_version:
        raise ProjectConfigError(
            f"{source}: missing required `schema_version` field."
        )
    _check_schema_version(schema_version)
    tools = _decode_tools(payload.get("tools"), source=source)
    return ToolchainLock(schema_version=schema_version, tools=dict(tools))


def read(path: Path) -> ToolchainLock:
    """Read and validate ``.alloy/toolchain.lock`` from disk.

    Raises :class:`ProjectConfigError` (Wave 1's typed error) when
    the file is malformed; mirroring the alloy.toml reader keeps the
    LLM-facing error_type contract simple.
    """
    if not path.exists():
        raise ProjectConfigError(
            f"{path}: toolchain.lock not found.  "
            "Run `alloy toolchain install` first."
        )
    with path.open("rb") as fp:
        try:
            payload = tomllib.load(fp)
        except tomllib.TOMLDecodeError as exc:
            raise ProjectConfigError(
                f"{path}: failed to parse as TOML — {exc}"
            ) from exc
    return parse(payload, source=str(path))


def read_optional(path: Path) -> ToolchainLock | None:
    """Read the lockfile, returning ``None`` instead of raising when missing.

    Convenient for callers that need to fall back to PATH-resolved
    binaries when no lockfile exists (the build / flash / debug
    backwards-compat path).
    """
    if not path.exists():
        return None
    return read(path)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _toml_escape(value: str) -> str:
    """Produce a basic TOML string literal (no multi-line)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dumps(lock: ToolchainLock) -> str:
    """Render a :class:`ToolchainLock` as deterministic TOML.

    Single source of truth for emission — both :func:`write` and
    any future code path that wants to compare the on-disk
    representation use this.
    """
    lines: list[str] = [
        f"schema_version = {_toml_escape(lock.schema_version)}",
        "",
    ]
    if lock.tools:
        lines.append("[tools]")
        # Alphabetical key order keeps git diffs sane and lets
        # `add(...)` produce stable output regardless of insert order.
        for name in sorted(lock.tools):
            pin = lock.tools[name]
            body = (
                f"{{ version = {_toml_escape(pin.version)}, "
                f"sha256 = {_toml_escape(pin.sha256)} }}"
            )
            lines.append(f"{_toml_escape(name)} = {body}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write(path: Path, lock: ToolchainLock) -> None:
    """Serialise to disk via :func:`dumps`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(lock), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def add(lock: ToolchainLock, tool: str, version: str, sha256: str) -> ToolchainLock:
    """Return a new lock with ``(version, sha256)`` pinned for ``tool``.

    Adding an existing tool overwrites its entry — semantically
    identical to ``alloy toolchain use <tool>@<version>``.
    """
    if not tool:
        raise ProjectConfigError("toolchain.lock: tool name must not be empty.")
    if not version:
        raise ProjectConfigError("toolchain.lock: version must not be empty.")
    if not sha256:
        raise ProjectConfigError("toolchain.lock: sha256 must not be empty.")
    new_tools = dict(lock.tools)
    new_tools[tool] = ToolchainPin(version=version, sha256=sha256)
    return ToolchainLock(schema_version=lock.schema_version, tools=new_tools)


def remove(lock: ToolchainLock, tool: str) -> ToolchainLock:
    """Return a new lock with ``tool`` removed (no-op when absent)."""
    if tool not in lock.tools:
        return lock
    new_tools = dict(lock.tools)
    del new_tools[tool]
    return ToolchainLock(schema_version=lock.schema_version, tools=new_tools)


def diff(before: ToolchainLock, after: ToolchainLock) -> tuple[ToolchainLockChange, ...]:
    """Compute a per-tool change list between two locks."""
    keys = set(before.tools) | set(after.tools)
    changes: list[ToolchainLockChange] = []
    for tool in sorted(keys):
        b = before.tools.get(tool)
        a = after.tools.get(tool)
        if b is None and a is not None:
            changes.append(ToolchainLockChange(tool=tool, kind="added", before=None, after=a))
        elif a is None and b is not None:
            changes.append(ToolchainLockChange(tool=tool, kind="removed", before=b, after=None))
        elif b is not None and a is not None and b != a:
            kind = (
                "version-changed"
                if b.version != a.version
                else "sha-changed"
            )
            changes.append(
                ToolchainLockChange(tool=tool, kind=kind, before=b, after=a)
            )
    return tuple(changes)


def empty() -> ToolchainLock:
    """Return a fresh empty lock at the current schema version."""
    return ToolchainLock(schema_version=SCHEMA_VERSION, tools={})


__all__ = [
    "LOCKFILE_NAME",
    "SCHEMA_VERSION",
    "ToolchainLock",
    "ToolchainLockChange",
    "ToolchainPin",
    "add",
    "diff",
    "dumps",
    "empty",
    "parse",
    "read",
    "read_optional",
    "remove",
    "write",
]
