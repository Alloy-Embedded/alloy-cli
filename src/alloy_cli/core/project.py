"""``alloy.toml`` reader, writer, and validator.

The single source of truth for what an Alloy project looks like.
Schema lives at ``schema/alloy_toml_v1.json`` (Draft 2020-12).
Read returns a typed :class:`ProjectConfig`; write produces
deterministic TOML so CI / TUI / MCP all round-trip identically.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from alloy_cli.core.errors import ProjectConfigError, ProjectConfigVersionError

PROJECT_FILE = "alloy.toml"
SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Typed view
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectMeta:
    name: str
    alloy_cli: str | None = None
    alloy: str | None = None
    alloy_codegen: str | None = None
    alloy_devices_yml: str | None = None


@dataclass(frozen=True, slots=True)
class BoardRef:
    """``[board]`` section."""

    id: str


@dataclass(frozen=True, slots=True)
class ChipRef:
    """``[chip]`` section — used when no board is involved."""

    vendor: str
    family: str
    device: str


@dataclass(frozen=True, slots=True)
class PeripheralEntry:
    """One ``[[peripherals]]`` entry — payload kept generic so
    every kind round-trips losslessly."""

    kind: str
    name: str
    payload: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Decoded ``alloy.toml`` body."""

    schema_version: str
    project: ProjectMeta
    board: BoardRef | None
    chip: ChipRef | None
    clocks: dict[str, Any]
    peripherals: tuple[PeripheralEntry, ...]
    build: dict[str, Any]
    flash: dict[str, Any]
    raw: dict[str, Any] = field(repr=False)


# ---------------------------------------------------------------------------
# Schema cache
# ---------------------------------------------------------------------------


def _load_schema() -> dict[str, Any]:
    """Load ``schema/alloy_toml_v1.json`` from the repo or installed package."""
    # Repo-local path first (development): schema/alloy_toml_v1.json
    repo_root = Path(__file__).resolve().parents[3]
    repo_schema = repo_root / "schema" / "alloy_toml_v1.json"
    if repo_schema.exists():
        return json.loads(repo_schema.read_text(encoding="utf-8"))
    # Fallback: try to locate via installed package data.
    try:
        with (
            resources.files("alloy_cli")
            .joinpath("schema/alloy_toml_v1.json")
            .open("r", encoding="utf-8") as fp
        ):
            return json.load(fp)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ProjectConfigError(
            "alloy.toml schema file not found.  "
            "Reinstall alloy-cli or check the development checkout."
        ) from exc


_VALIDATOR: Draft202012Validator | None = None


def _validator() -> Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        _VALIDATOR = Draft202012Validator(_load_schema())
    return _VALIDATOR


# ---------------------------------------------------------------------------
# Read + decode
# ---------------------------------------------------------------------------


def _check_schema_version(text_version: str) -> None:
    parts = text_version.split(".")
    if len(parts) != 3 or not parts[0].isdigit():
        raise ProjectConfigError(
            f"alloy.toml schema_version {text_version!r} is not a 3-segment SemVer string."
        )
    major = int(parts[0])
    if major != 1:
        raise ProjectConfigVersionError(
            f"alloy.toml declares schema_version {text_version!r} "
            f"(major={major}); this alloy-cli understands major=1.  "
            f"Run `alloy update` to upgrade alloy-cli."
        )


def _decode_peripherals(raw: list[dict[str, Any]]) -> tuple[PeripheralEntry, ...]:
    items: list[PeripheralEntry] = []
    for entry in raw:
        kind = entry.get("kind", "")
        name = entry.get("name", "")
        items.append(PeripheralEntry(kind=str(kind), name=str(name), payload=dict(entry)))
    return tuple(items)


def parse(payload: dict[str, Any]) -> ProjectConfig:
    """Validate + decode an already-parsed TOML payload.

    Useful for tests and the CMake bridge that hands us a dict.
    """
    schema_version = payload.get("schema_version", "")
    if not schema_version:
        raise ProjectConfigError("alloy.toml is missing the required `schema_version` field.")
    _check_schema_version(str(schema_version))

    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        details = "\n".join(
            f"  • {'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise ProjectConfigError(f"alloy.toml failed schema validation:\n{details}")

    project_raw = payload.get("project", {})
    project = ProjectMeta(
        name=str(project_raw["name"]),
        alloy_cli=project_raw.get("alloy-cli"),
        alloy=project_raw.get("alloy"),
        alloy_codegen=project_raw.get("alloy-codegen"),
        alloy_devices_yml=project_raw.get("alloy-devices-yml"),
    )

    board_raw = payload.get("board")
    board = BoardRef(id=str(board_raw["id"])) if board_raw else None
    chip_raw = payload.get("chip")
    chip = (
        ChipRef(
            vendor=str(chip_raw["vendor"]),
            family=str(chip_raw["family"]),
            device=str(chip_raw["device"]),
        )
        if chip_raw
        else None
    )

    return ProjectConfig(
        schema_version=str(schema_version),
        project=project,
        board=board,
        chip=chip,
        clocks=dict(payload.get("clocks", {})),
        peripherals=_decode_peripherals(list(payload.get("peripherals", []))),
        build=dict(payload.get("build", {})),
        flash=dict(payload.get("flash", {})),
        raw=payload,
    )


def read(path: Path) -> ProjectConfig:
    """Read and validate ``alloy.toml`` from disk."""
    if not path.exists():
        raise ProjectConfigError(f"{path}: alloy.toml not found.  Run `alloy new` first.")
    with path.open("rb") as fp:
        payload = tomllib.load(fp)
    return parse(payload)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _toml_value(value: Any) -> str:
    """Render a Python value as a TOML scalar (no compound types)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        # naive quoting; alloy.toml rarely contains backslashes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise TypeError(f"Cannot render {type(value).__name__} as TOML scalar")


def _toml_array(values: list[Any]) -> str:
    return "[" + ", ".join(_toml_value(v) for v in values) + "]"


def _emit_section(name: str, body: dict[str, Any]) -> list[str]:
    if not body:
        return []
    lines = [f"[{name}]"]
    for key, value in body.items():
        if isinstance(value, list):
            lines.append(f"{key} = {_toml_array(value)}")
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    lines.append("")
    return lines


def _emit_peripheral(entry: PeripheralEntry) -> list[str]:
    lines = ["[[peripherals]]"]
    payload = dict(entry.payload)
    payload.setdefault("kind", entry.kind)
    payload.setdefault("name", entry.name)
    # Keep `kind` and `name` first for readability.
    ordered_keys = ["kind", "name", *(k for k in payload if k not in {"kind", "name"})]
    for key in ordered_keys:
        value = payload[key]
        if isinstance(value, list):
            lines.append(f"{key} = {_toml_array(value)}")
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    lines.append("")
    return lines


def write(path: Path, config: ProjectConfig) -> None:
    """Serialise a ``ProjectConfig`` to a deterministic TOML file."""
    lines: list[str] = [
        f'schema_version = "{config.schema_version}"',
        "",
        "[project]",
        f'name = "{config.project.name}"',
    ]
    if config.project.alloy_cli is not None:
        lines.append(f'alloy-cli = "{config.project.alloy_cli}"')
    if config.project.alloy is not None:
        lines.append(f'alloy = "{config.project.alloy}"')
    if config.project.alloy_codegen is not None:
        lines.append(f'alloy-codegen = "{config.project.alloy_codegen}"')
    if config.project.alloy_devices_yml is not None:
        lines.append(f'alloy-devices-yml = "{config.project.alloy_devices_yml}"')
    lines.append("")

    if config.board is not None:
        lines.extend(["[board]", f'id = "{config.board.id}"', ""])
    if config.chip is not None:
        lines.extend(
            [
                "[chip]",
                f'vendor = "{config.chip.vendor}"',
                f'family = "{config.chip.family}"',
                f'device = "{config.chip.device}"',
                "",
            ]
        )

    lines.extend(_emit_section("clocks", config.clocks))

    for peripheral in config.peripherals:
        lines.extend(_emit_peripheral(peripheral))

    lines.extend(_emit_section("build", config.build))
    lines.extend(_emit_section("flash", config.flash))

    text = "\n".join(lines).rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# .alloy/ cache layout
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlloyDir:
    """Resolves the ``.alloy/`` cache layout under a project root."""

    root: Path

    @property
    def base(self) -> Path:
        return self.root / ".alloy"

    @property
    def lockfile(self) -> Path:
        return self.base / "version.lock"

    @property
    def cache(self) -> Path:
        return self.base / "cache"

    @property
    def generated(self) -> Path:
        return self.base / "generated"

    def ensure(self) -> None:
        for subdir in (self.cache, self.generated):
            subdir.mkdir(parents=True, exist_ok=True)


__all__ = [
    "PROJECT_FILE",
    "SCHEMA_VERSION",
    "AlloyDir",
    "BoardRef",
    "ChipRef",
    "PeripheralEntry",
    "ProjectConfig",
    "ProjectMeta",
    "parse",
    "read",
    "write",
]
