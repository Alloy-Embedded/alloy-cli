"""Per-MCU-family toolchain manifest loader.

Reads ``data/families/<family_id>.yml``, validates against
``schema/family_toolchain_v1.json`` (Draft 2020-12), resolves the
``extends:`` chain, and projects the merged result to typed
:class:`FamilyManifest` / :class:`ToolRequirement` views.

The manifests describe *host-side* toolchain expectations per MCU
family — which compiler, which flasher, which recovery tool, where
each one comes from (xpack / github / probe-rs-installer / espressif /
vendor).  Wave 1 only consumes them for ``alloy doctor`` rendering;
Wave 2 hangs the actual installer off the same source vocabulary
without needing to re-parse anything.

Cache layout mirrors :mod:`core.ir` — first parse of a manifest is
pickled under ``.alloy/cache/families/<family_id>.pkl`` keyed on
``sha256(yaml_text + parents_yaml_text + alloy_cli_version)``.
"""

from __future__ import annotations

import hashlib
import pickle
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from alloy_cli import __version__ as _alloy_cli_version
from alloy_cli.core.errors import (
    FamilyToolchainCycleError,
    FamilyToolchainNotFoundError,
    FamilyToolchainSchemaError,
    FamilyToolchainUnknownParentError,
)
from alloy_cli.core.project import ProjectConfig

SCHEMA_VERSION = "1.0.0"
SCHEMA_FILE = "family_toolchain_v1.json"
FAMILIES_DIRNAME = "families"

# ---------------------------------------------------------------------------
# Typed views
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolRequirement:
    """One row in a family's required / recommended / optional list."""

    tool: str
    version: str
    source: str
    capabilities: tuple[str, ...]
    bundles: tuple[str, ...] = ()
    udev_required: bool = False
    install_docs: dict[str, str] = field(default_factory=dict)

    @property
    def is_vendor(self) -> bool:
        """True iff this tool is EULA-gated (manual install only)."""
        return self.source == "vendor"

    @property
    def all_provided_binaries(self) -> tuple[str, ...]:
        """The primary tool name plus every bundled binary."""
        return (self.tool, *self.bundles)

    def provides_capability(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True, slots=True)
class FamilyManifest:
    """Resolved per-MCU-family toolchain manifest.

    The arrays here have already been merged across the
    ``extends:`` chain — child entries override base entries by
    ``tool`` name.
    """

    family_id: str
    core: str
    arch: str | None
    schema_version: str
    required: tuple[ToolRequirement, ...]
    recommended: tuple[ToolRequirement, ...]
    optional: tuple[ToolRequirement, ...]
    extends: str | None = None
    chain: tuple[str, ...] = ()  # parents in load order, e.g. ("arm-cortex-m",)

    def all_tools(self) -> tuple[ToolRequirement, ...]:
        """Required + recommended + optional in priority order."""
        return (*self.required, *self.recommended, *self.optional)

    def tool_for_capability(self, capability: str) -> ToolRequirement | None:
        """Return the first tool advertising ``capability``.

        Searches required → recommended → optional in that order.
        Bundled binaries don't count — capabilities are declared on
        the primary tool, so a gcc bundling gdb advertises both
        ``build`` and ``debug`` on the gcc requirement itself.
        """
        for tool in self.all_tools():
            if tool.provides_capability(capability):
                return tool
        return None

    def find_tool(self, name: str) -> ToolRequirement | None:
        """Look up a tool by its canonical name (or by a bundled alias)."""
        for tool in self.all_tools():
            if tool.tool == name or name in tool.bundles:
                return tool
        return None


# ---------------------------------------------------------------------------
# Locator + schema loader (dual repo / package data)
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _repo_schema_path() -> Path:
    return _REPO_ROOT / "schema" / SCHEMA_FILE


def _repo_families_dir() -> Path:
    return _REPO_ROOT / "data" / FAMILIES_DIRNAME


def _repo_manifest_path(family_id: str) -> Path:
    return _repo_families_dir() / f"{family_id}.yml"


def _load_schema_dict() -> dict[str, Any]:
    """Load the family-toolchain JSON Schema (repo path → wheel data)."""
    repo_path = _repo_schema_path()
    if repo_path.exists():
        import json

        return json.loads(repo_path.read_text(encoding="utf-8"))
    try:
        with (
            resources.files("alloy_cli")
            .joinpath(f"schema/{SCHEMA_FILE}")
            .open("r", encoding="utf-8") as fp
        ):
            import json

            return json.load(fp)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise FamilyToolchainSchemaError(
            f"family-toolchain schema {SCHEMA_FILE!r} not found.  "
            "Reinstall alloy-cli or check the development checkout."
        ) from exc


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = _load_schema_dict()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _read_manifest_text(family_id: str) -> str:
    """Return the raw YAML text for ``family_id`` (repo → wheel)."""
    repo_path = _repo_manifest_path(family_id)
    if repo_path.exists():
        return repo_path.read_text(encoding="utf-8")
    try:
        with (
            resources.files("alloy_cli")
            .joinpath(f"data/{FAMILIES_DIRNAME}/{family_id}.yml")
            .open("r", encoding="utf-8") as fp
        ):
            return fp.read()
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise FamilyToolchainNotFoundError(
            f"No family manifest found for {family_id!r}.  "
            f"Known families: {', '.join(known_families()) or '(none)'}."
        ) from exc


@lru_cache(maxsize=1)
def known_families() -> tuple[str, ...]:
    """Return every family id alloy-cli ships a manifest for, sorted."""
    seen: set[str] = set()
    repo_dir = _repo_families_dir()
    if repo_dir.exists():
        seen.update(p.stem for p in repo_dir.glob("*.yml"))
    try:
        anchor = resources.files("alloy_cli").joinpath(f"data/{FAMILIES_DIRNAME}")
        if anchor.is_dir():
            for entry in anchor.iterdir():
                name = entry.name
                if name.endswith(".yml"):
                    seen.add(name.removesuffix(".yml"))
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return tuple(sorted(seen))


# ---------------------------------------------------------------------------
# Parse + validate
# ---------------------------------------------------------------------------


def _parse_one(family_id: str) -> tuple[dict[str, Any], str]:
    """Load + validate one manifest YAML.

    Returns the parsed dict and the raw text (the latter is hashed
    into the cache key, so we surface it to the caller rather than
    re-reading the file).
    """
    text = _read_manifest_text(family_id)
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise FamilyToolchainSchemaError(
            f"{family_id}.yml: expected a YAML mapping at the root, got "
            f"{type(payload).__name__}."
        )

    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        details = "\n".join(
            f"  • /{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise FamilyToolchainSchemaError(
            f"{family_id}.yml failed family-toolchain schema validation:\n{details}"
        )
    return payload, text


# ---------------------------------------------------------------------------
# Extends-chain resolution
# ---------------------------------------------------------------------------


def _resolve_chain(family_id: str) -> list[tuple[str, dict[str, Any], str]]:
    """Walk the extends chain from root → leaf.

    Returns a list of ``(family_id, payload, raw_text)`` tuples in
    *base-first* order.  The top entry is the bottom of the
    inheritance graph (no ``extends``), the last entry is the
    requested family.

    Raises:
      FamilyToolchainCycleError on cycles.
      FamilyToolchainUnknownParentError on missing parents.
      FamilyToolchainSchemaError / FamilyToolchainNotFoundError per
      :func:`_parse_one`.
    """
    visited: list[str] = []
    payload, text = _parse_one(family_id)
    chain: list[tuple[str, dict[str, Any], str]] = [(family_id, payload, text)]
    visited.append(family_id)

    current_payload = payload
    while True:
        parent = current_payload.get("extends")
        if not parent:
            break
        if parent in visited:
            cycle = " → ".join([*visited, parent])
            raise FamilyToolchainCycleError(
                f"family-toolchain extends chain forms a cycle: {cycle}."
            )
        try:
            parent_payload, parent_text = _parse_one(parent)
        except FamilyToolchainNotFoundError as exc:
            raise FamilyToolchainUnknownParentError(
                f"{visited[-1]}.yml declares extends: {parent!r}, but no manifest "
                f"exists for that family."
            ) from exc
        chain.append((parent, parent_payload, parent_text))
        visited.append(parent)
        current_payload = parent_payload

    # Reverse so callers walk base → child when merging.
    chain.reverse()
    return chain


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _merge_tools(
    base: list[dict[str, Any]] | None, overlay: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Merge two tool lists by ``tool`` name.

    Overlay entries with a ``tool`` key already in the base replace
    the base entry in place (preserving order); new overlay entries
    append.
    """
    base_list = list(base or [])
    overlay_list = list(overlay or [])
    if not overlay_list:
        return base_list

    indexed: dict[str, int] = {entry["tool"]: i for i, entry in enumerate(base_list) if "tool" in entry}
    result: list[dict[str, Any]] = list(base_list)
    for entry in overlay_list:
        name = entry.get("tool")
        if isinstance(name, str) and name in indexed:
            result[indexed[name]] = entry
        else:
            result.append(entry)
            if isinstance(name, str):
                indexed[name] = len(result) - 1
    return result


def _merge_chain(chain: Iterable[tuple[str, dict[str, Any], str]]) -> dict[str, Any]:
    """Walk base→child and produce a single merged manifest payload.

    Required / recommended / optional arrays merge by tool name (see
    :func:`_merge_tools`).  Other top-level fields take the *child's*
    value (last write wins) — that matches the design rule "child
    overrides base."
    """
    merged: dict[str, Any] = {}
    for entry in chain:
        payload = entry[1]
        for key, value in payload.items():
            if key in {"required", "recommended", "optional"}:
                merged[key] = _merge_tools(merged.get(key), value)
            elif key == "extends":
                # `extends` is a per-file directive, not a runtime
                # property of the resolved manifest.  We carry the
                # leaf's `extends` separately on FamilyManifest so
                # introspection stays useful.
                continue
            else:
                merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def _project_tool(payload: dict[str, Any]) -> ToolRequirement:
    return ToolRequirement(
        tool=str(payload["tool"]),
        version=str(payload["version"]),
        source=str(payload["source"]),
        capabilities=tuple(payload.get("capabilities") or ()),
        bundles=tuple(payload.get("bundles") or ()),
        udev_required=bool(payload.get("udev_required", False)),
        install_docs=dict(payload.get("install_docs") or {}),
    )


def _project_manifest(
    merged: dict[str, Any],
    chain: list[tuple[str, dict[str, Any], str]],
    leaf_extends: str | None,
) -> FamilyManifest:
    parents = tuple(entry[0] for entry in chain[:-1])  # everything except the leaf
    return FamilyManifest(
        family_id=str(merged["family_id"]),
        core=str(merged["core"]),
        arch=merged.get("arch"),
        schema_version=str(merged["schema_version"]),
        required=tuple(_project_tool(t) for t in merged.get("required") or ()),
        recommended=tuple(_project_tool(t) for t in merged.get("recommended") or ()),
        optional=tuple(_project_tool(t) for t in merged.get("optional") or ()),
        extends=leaf_extends,
        chain=parents,
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    cache = _REPO_ROOT / ".alloy" / "cache" / "families"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _cache_key(chain_texts: Iterable[str]) -> str:
    """SHA256 of every YAML in the chain + alloy-cli version."""
    sha = hashlib.sha256()
    for text in chain_texts:
        sha.update(text.encode("utf-8"))
        sha.update(b"\x00")
    sha.update(_alloy_cli_version.encode("utf-8"))
    return sha.hexdigest()[:16]


def _cache_path(family_id: str) -> Path:
    return _cache_dir() / f"{family_id}.pkl"


def _read_cached(family_id: str, expected_key: str) -> FamilyManifest | None:
    path = _cache_path(family_id)
    if not path.exists():
        return None
    try:
        with path.open("rb") as fp:
            cached = pickle.load(fp)
    except (pickle.UnpicklingError, EOFError, AttributeError, ImportError):
        return None
    if not isinstance(cached, dict) or cached.get("key") != expected_key:
        return None
    manifest = cached.get("manifest")
    return manifest if isinstance(manifest, FamilyManifest) else None


def _write_cache(family_id: str, key: str, manifest: FamilyManifest) -> None:
    path = _cache_path(family_id)
    try:
        with path.open("wb") as fp:
            pickle.dump({"key": key, "manifest": manifest}, fp)
    except OSError:
        # Cache is best-effort — never break a load just because
        # the cache directory is read-only.
        return


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_family(family_id: str) -> FamilyManifest:
    """Load + resolve + cache the manifest for ``family_id``.

    Raises:
      FamilyToolchainNotFoundError when no YAML ships for the id.
      FamilyToolchainSchemaError when the YAML fails JSON-Schema
        validation.
      FamilyToolchainUnknownParentError when an ``extends:`` target
        has no manifest.
      FamilyToolchainCycleError when the extends chain cycles.
    """
    chain = _resolve_chain(family_id)
    chain_key = _cache_key(entry[2] for entry in chain)

    cached = _read_cached(family_id, chain_key)
    if cached is not None:
        return cached

    leaf_payload = chain[-1][1]
    leaf_extends = leaf_payload.get("extends")
    merged = _merge_chain(chain)
    manifest = _project_manifest(merged, chain, leaf_extends)
    _write_cache(family_id, chain_key, manifest)
    return manifest


def resolve_for_project(config: ProjectConfig) -> FamilyManifest | None:
    """Return the manifest that matches the project's target, or ``None``.

    Resolution order:
      1. ``config.chip.family`` when ``[chip]`` is set.
      2. ``boards.lookup(config.board.id).family`` when ``[board]``
         is set.
      3. ``None`` otherwise.

    Never raises for a missing manifest — callers fall back to the
    legacy generic check list when this returns ``None``.  Schema /
    cycle / unknown-parent errors *do* propagate, since those are
    bugs in alloy-cli's own data, not user-fixable.
    """
    family_id: str | None = None
    if config.chip is not None:
        family_id = config.chip.family
    elif config.board is not None:
        # Lazy import — keeps boards.lookup off the import graph for
        # callers that only ever see chip-only projects.
        from alloy_cli.core import boards as _boards
        from alloy_cli.core.errors import BoardNotFoundError

        try:
            manifest = _boards.lookup(config.board.id)
        except BoardNotFoundError:
            return None
        family_id = manifest.family

    if not family_id:
        return None

    try:
        return load_family(family_id)
    except FamilyToolchainNotFoundError:
        return None


__all__ = [
    "FAMILIES_DIRNAME",
    "SCHEMA_FILE",
    "SCHEMA_VERSION",
    "FamilyManifest",
    "ToolRequirement",
    "known_families",
    "load_family",
    "resolve_for_project",
]
