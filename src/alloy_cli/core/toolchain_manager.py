"""Content-addressed toolchain store + atomic install pipeline.

Wave 2's beating heart: takes a :class:`SourceArtifact` (resolved by
``core.tool_sources`` from the pinned URL+SHA tables) and:

  1. acquires the advisory file lock so concurrent installs from
     different alloy-cli processes serialise;
  2. streams the bytes through the active :class:`Downloader`,
     verifying SHA256 on the wire so a tampered tarball never lands
     on disk;
  3. extracts into a temp tree, sanitising path-traversal attempts
     (``tarfile.data_filter`` on Python 3.12+; manual scrub
     otherwise);
  4. atomically promotes the extraction via ``os.rename`` to
     ``<store>/<sha>/`` — that's the commit boundary;
  5. drops a ``by-name/<tool>/<version>`` symlink (POSIX) or
     pointer file (Windows) so consumers find binaries by friendly
     name;
  6. updates ``manifest.json`` under the same lock;
  7. on Linux, when the family manifest declared
     ``udev_required: true``, writes the rules content and emits
     the explicit ``sudo`` instruction — never invoking sudo
     itself.

Layout (resolved via :func:`platformdirs.user_data_dir`):

    <user_data>/alloy/tools/
    ├── store/<sha256>/           # immutable, one per content hash
    ├── store/.tmp/<sha256>...    # in-flight downloads + extractions
    ├── by-name/<tool>/<version>  # symlink → ../../store/<sha256>
    │                             # (or pointer dir on Windows)
    ├── manifest.json             # registry of installed tools
    ├── udev/<tool>.rules         # Linux probe rules awaiting sudo cp
    └── .lock                     # advisory file lock
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tarfile
import time
import zipfile
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import platformdirs

from alloy_cli.core import tool_sources as _ts
from alloy_cli.core.errors import (
    FamilyToolchainInstallerExtractError,
    FamilyToolchainInstallerLockedError,
    FamilyToolchainInstallerStoreCorruptError,
)
from alloy_cli.core.lockfile_toolchain import (
    LOCKFILE_NAME,
    ToolchainLock,
    read_optional,
)
from alloy_cli.core.tool_sources import Downloader, SourceArtifact

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0.0"
TMP_SWEEP_AGE_S = 60 * 60  # one hour

# ---------------------------------------------------------------------------
# Typed views
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstalledTool:
    """One tool present in the store (one entry in manifest.json)."""

    tool: str
    version: str
    source: str
    sha256: str
    store_path: Path
    primary_binary: str
    binaries: tuple[str, ...]
    installed_at: str  # ISO-8601 UTC

    def absolute_primary(self) -> Path:
        return self.store_path / self.primary_binary

    def absolute_binary(self, name: str) -> Path | None:
        for rel in self.binaries:
            if Path(rel).name == name or rel == name:
                return self.store_path / rel
        return None


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    """Result of a single :func:`install` call."""

    tool: str
    version: str
    sha256: str
    skipped: bool
    store_path: Path
    bytes_downloaded: int
    udev_rules_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PruneCandidate:
    """One store entry eligible for deletion."""

    tool: str
    version: str
    sha256: str
    store_path: Path
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PruneReport:
    """Outcome of :func:`prune`."""

    candidates: tuple[PruneCandidate, ...]
    deleted: tuple[PruneCandidate, ...]
    bytes_freed: int = 0
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Store layout
# ---------------------------------------------------------------------------


def store_root() -> Path:
    """Resolve the toolchain store root via :mod:`platformdirs`.

    Honours the ``ALLOY_TOOLS_ROOT`` environment variable when set so
    tests + CI can redirect to a tmp dir without touching the real
    user data directory.
    """
    override = os.environ.get("ALLOY_TOOLS_ROOT")
    if override:
        return Path(override).resolve()
    return Path(platformdirs.user_data_dir("alloy")) / "tools"


def _store_subdir(sha: str) -> Path:
    return store_root() / "store" / sha


def _tmp_dir() -> Path:
    return store_root() / "store" / ".tmp"


def _by_name_dir() -> Path:
    return store_root() / "by-name"


def _manifest_path() -> Path:
    return store_root() / MANIFEST_NAME


def _lock_path() -> Path:
    return store_root() / ".lock"


def _udev_dir() -> Path:
    return store_root() / "udev"


def ensure_store() -> None:
    """Create the layout idempotently."""
    root = store_root()
    (root / "store").mkdir(parents=True, exist_ok=True)
    _tmp_dir().mkdir(parents=True, exist_ok=True)
    _by_name_dir().mkdir(parents=True, exist_ok=True)
    _udev_dir().mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Advisory file lock
# ---------------------------------------------------------------------------


@contextmanager
def _store_lock():  # type: ignore[no-untyped-def]
    """Acquire the store's advisory file lock; raise the typed error
    when another process holds it.

    POSIX uses ``fcntl.flock(LOCK_EX | LOCK_NB)``; Windows uses
    ``msvcrt.locking(LK_NBLCK, 1)``.
    """
    ensure_store()
    lock_path = _lock_path()
    lock_path.touch(exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR)
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise FamilyToolchainInstallerLockedError(
                    f"another process holds the toolchain store lock at "
                    f"{lock_path}.  Wait for it to finish and retry."
                ) from exc
            try:
                yield
            finally:
                try:
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise FamilyToolchainInstallerLockedError(
                    f"another process holds the toolchain store lock at "
                    f"{lock_path}.  Wait for it to finish and retry."
                ) from exc
            try:
                yield
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# manifest.json
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _read_manifest() -> dict[str, Any]:
    path = _manifest_path()
    if not path.exists():
        return {"schema_version": MANIFEST_SCHEMA_VERSION, "tools": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": MANIFEST_SCHEMA_VERSION, "tools": []}
    if not isinstance(payload, dict):
        return {"schema_version": MANIFEST_SCHEMA_VERSION, "tools": []}
    payload.setdefault("schema_version", MANIFEST_SCHEMA_VERSION)
    payload.setdefault("tools", [])
    if not isinstance(payload["tools"], list):
        payload["tools"] = []
    return payload


def _write_manifest_atomically(payload: dict[str, Any]) -> None:
    """Write manifest.json via temp-file + os.rename so a kill mid-write
    leaves the previous (valid) manifest in place."""
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _entries_to_installed(entries: Iterable[dict[str, Any]]) -> list[InstalledTool]:
    out: list[InstalledTool] = []
    for entry in entries:
        try:
            out.append(
                InstalledTool(
                    tool=str(entry["tool"]),
                    version=str(entry["version"]),
                    source=str(entry["source"]),
                    sha256=str(entry["sha256"]),
                    store_path=Path(str(entry["store_path"])),
                    primary_binary=str(entry["primary_binary"]),
                    binaries=tuple(entry.get("binaries", []) or ()),
                    installed_at=str(entry.get("installed_at", "")),
                )
            )
        except (KeyError, TypeError):
            # Skip malformed entries — verify() will surface them as
            # store corruption later.
            continue
    return out


def _installed_to_entry(tool: InstalledTool) -> dict[str, Any]:
    return {
        "tool": tool.tool,
        "version": tool.version,
        "source": tool.source,
        "sha256": tool.sha256,
        "store_path": str(tool.store_path),
        "primary_binary": tool.primary_binary,
        "binaries": list(tool.binaries),
        "installed_at": tool.installed_at,
    }


def list_installed() -> list[InstalledTool]:
    """Return every entry currently in ``manifest.json``."""
    payload = _read_manifest()
    return _entries_to_installed(payload.get("tools", []))


def _find_entry(
    payload: dict[str, Any], *, tool: str, version: str | None, sha: str | None
) -> tuple[int, dict[str, Any]] | None:
    for idx, entry in enumerate(payload.get("tools", []) or ()):
        if not isinstance(entry, dict):
            continue
        if entry.get("tool") != tool:
            continue
        if version is not None and entry.get("version") != version:
            continue
        if sha is not None and entry.get("sha256") != sha:
            continue
        return idx, entry
    return None


# ---------------------------------------------------------------------------
# Symlink / pointer
# ---------------------------------------------------------------------------


def _link_by_name(tool: str, version: str, store_path: Path) -> Path:
    """Create the human-friendly ``by-name/<tool>/<version>`` shortcut.

    POSIX: symlink to the store directory.  Windows (or any host
    where symlinks fail with ``OSError``): write a ``_pointer.txt``
    file containing the absolute store path.
    """
    base = _by_name_dir() / tool / version
    base.parent.mkdir(parents=True, exist_ok=True)
    # Remove any existing entry first so re-installs work.
    if base.is_symlink() or base.is_file():
        base.unlink()
    elif base.is_dir():
        shutil.rmtree(base)

    if sys.platform == "win32":
        return _write_pointer(base, store_path)
    try:
        base.symlink_to(store_path)
        return base
    except (OSError, NotImplementedError):
        # Windows without admin rights, or filesystems that reject
        # symlinks (some network mounts) — fall back to a pointer
        # file pattern.
        return _write_pointer(base, store_path)


def _write_pointer(base: Path, store_path: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "_pointer.txt").write_text(str(store_path), encoding="utf-8")
    return base


def _resolve_by_name(tool: str, version: str) -> Path | None:
    base = _by_name_dir() / tool / version
    if base.is_symlink():
        target = base.resolve()
        if target.is_dir():
            return target
        return None
    pointer = base / "_pointer.txt"
    if pointer.exists():
        try:
            target = Path(pointer.read_text(encoding="utf-8").strip())
            return target if target.is_dir() else None
        except OSError:
            return None
    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _safe_resolve(member: str, dest: Path) -> Path:
    """Resolve a member path against ``dest`` and refuse path traversal."""
    candidate = (dest / member).resolve()
    try:
        candidate.relative_to(dest.resolve())
    except ValueError as exc:
        raise FamilyToolchainInstallerExtractError(
            f"refusing to write outside extraction root: {member}"
        ) from exc
    return candidate


def _extract_tar(archive: Path, dest: Path) -> None:
    try:
        with tarfile.open(archive, mode="r:*") as tar:
            if sys.version_info >= (3, 12):
                tar.extractall(dest, filter="data")
            else:
                # Python ≤ 3.11: hand-rolled sanitisation.
                for member in tar.getmembers():
                    if member.name.startswith("/"):
                        raise FamilyToolchainInstallerExtractError(
                            f"refusing absolute member path: {member.name}"
                        )
                    if any(part == ".." for part in Path(member.name).parts):
                        raise FamilyToolchainInstallerExtractError(
                            f"refusing path-traversal member: {member.name}"
                        )
                    _safe_resolve(member.name, dest)
                tar.extractall(dest)
    except (tarfile.TarError, OSError) as exc:
        raise FamilyToolchainInstallerExtractError(
            f"failed to extract {archive.name}: {exc}"
        ) from exc


def _extract_zip(archive: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.startswith("/"):
                    raise FamilyToolchainInstallerExtractError(
                        f"refusing absolute member path: {name}"
                    )
                if any(part == ".." for part in Path(name).parts):
                    raise FamilyToolchainInstallerExtractError(
                        f"refusing path-traversal member: {name}"
                    )
                _safe_resolve(name, dest)
            zf.extractall(dest)
    except (zipfile.BadZipFile, OSError) as exc:
        raise FamilyToolchainInstallerExtractError(
            f"failed to extract {archive.name}: {exc}"
        ) from exc


def _extract(archive: Path, archive_kind: str, dest: Path) -> None:
    """Dispatch by archive_kind.  ``bin`` means single-file binary
    (e.g. probe-rs ships static binaries on some hosts) — copy as-is."""
    dest.mkdir(parents=True, exist_ok=True)
    if archive_kind in {"tar.xz", "tar.gz", "tar.bz2"}:
        _extract_tar(archive, dest)
    elif archive_kind == "zip":
        _extract_zip(archive, dest)
    elif archive_kind == "bin":
        shutil.copy2(archive, dest / archive.name)
    else:
        raise FamilyToolchainInstallerExtractError(
            f"unsupported archive_kind {archive_kind!r}"
        )


def _flatten_subdir(extract_root: Path, subdir: str) -> None:
    """When the archive ships a single top-level directory (xpack
    convention), move its contents up to ``extract_root`` and
    delete the empty parent so the store layout stays predictable.
    """
    if not subdir:
        return
    nested = extract_root / subdir
    if not nested.is_dir():
        # Archive may not actually contain the declared subdir on every
        # host — silently no-op in that case so a misconfigured pin
        # doesn't crash extraction.
        return
    for child in nested.iterdir():
        target = extract_root / child.name
        if target.exists():
            # Conflict between the subdir's content and an existing
            # entry — refuse to silently overwrite.
            raise FamilyToolchainInstallerExtractError(
                f"flatten conflict: {target.name} would be overwritten"
            )
        child.rename(target)
    nested.rmdir()


# ---------------------------------------------------------------------------
# udev rules emission
# ---------------------------------------------------------------------------


def _emit_udev_rules(
    artifact: SourceArtifact,
    *,
    on_line: Callable[[str], None] | None,
) -> Path | None:
    """Write Linux probe udev rules; never invoke sudo.

    On macOS / Windows this is a silent no-op, matching the family
    manifest semantics for ``udev_required``.
    """
    if not artifact.udev_rules:
        return None
    if platform.system() != "Linux":
        return None

    udev_dir = _udev_dir()
    udev_dir.mkdir(parents=True, exist_ok=True)
    rules_path = udev_dir / f"{artifact.tool}.rules"
    rules_path.write_text(artifact.udev_rules, encoding="utf-8")

    if on_line is not None:
        on_line(f"  Wrote udev rules to {rules_path}")
        on_line("  Run this once to enable non-root probe access:")
        on_line(f"    sudo cp {rules_path} /etc/udev/rules.d/")
        on_line("    sudo udevadm control --reload-rules")
    return rules_path


# ---------------------------------------------------------------------------
# tmp sweep
# ---------------------------------------------------------------------------


def _sweep_stale_tmp() -> None:
    """Delete ``store/.tmp/*`` entries older than :data:`TMP_SWEEP_AGE_S`.

    Catches partial downloads / extractions left by a previous
    alloy-cli that was killed mid-install.
    """
    tmp = _tmp_dir()
    if not tmp.exists():
        return
    cutoff = time.time() - TMP_SWEEP_AGE_S
    for entry in tmp.iterdir():
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API: install
# ---------------------------------------------------------------------------


def install(
    artifact: SourceArtifact,
    *,
    force: bool = False,
    downloader: Downloader | None = None,
    on_line: Callable[[str], None] | None = None,
) -> InstallOutcome:
    """Atomically install ``artifact`` into the content-addressed store.

    Idempotent: re-running on an already-promoted artefact returns
    ``InstallOutcome(skipped=True)`` without touching the network.

    Raises:
      FamilyToolchainInstallerLockedError when another process
        holds the store's advisory lock.
      FamilyToolchainInstallerChecksumError if the downloader
        detects a SHA256 mismatch on the wire.
      FamilyToolchainInstallerExtractError when the archive
        contains path-traversal members or is corrupt.
    """
    dl = downloader if downloader is not None else _ts.downloader
    with _store_lock():
        ensure_store()
        _sweep_stale_tmp()

        sha = artifact.sha256
        store_path = _store_subdir(sha)

        # Idempotency: same SHA already present + manifest in sync.
        if store_path.is_dir() and not force:
            payload = _read_manifest()
            existing = _find_entry(
                payload, tool=artifact.tool, version=artifact.version, sha=sha
            )
            if existing is not None:
                _link_by_name(artifact.tool, artifact.version, store_path)
                if on_line is not None:
                    on_line(
                        f"  {artifact.tool} {artifact.version} already in store"
                    )
                return InstallOutcome(
                    tool=artifact.tool,
                    version=artifact.version,
                    sha256=sha,
                    skipped=True,
                    store_path=store_path,
                    bytes_downloaded=0,
                )

        # ── 1. Download to .tmp/<sha>.partial (handled by Downloader)
        partial_archive = _tmp_dir() / f"{sha}.archive"
        if partial_archive.exists():
            partial_archive.unlink()
        if on_line is not None:
            on_line(
                f"  Downloading {artifact.tool} {artifact.version} "
                f"({artifact.url})"
            )
        dl.fetch(artifact, partial_archive)
        bytes_downloaded = partial_archive.stat().st_size

        # ── 2. Extract to .tmp/<sha>/
        tmp_extract = _tmp_dir() / sha
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract)
        try:
            _extract(partial_archive, artifact.archive_kind, tmp_extract)
            _flatten_subdir(tmp_extract, artifact.extract_to_subdir)
        except Exception:
            shutil.rmtree(tmp_extract, ignore_errors=True)
            partial_archive.unlink(missing_ok=True)
            raise

        # ── 3. Promote: os.rename is atomic on the same FS
        if store_path.exists():
            # Force re-install path
            shutil.rmtree(store_path)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        os.rename(tmp_extract, store_path)
        partial_archive.unlink(missing_ok=True)

        # ── 4. Symlink / pointer
        _link_by_name(artifact.tool, artifact.version, store_path)

        # ── 5. udev rules (Linux only)
        udev_path = _emit_udev_rules(artifact, on_line=on_line)

        # ── 6. Manifest update
        installed = InstalledTool(
            tool=artifact.tool,
            version=artifact.version,
            source=artifact.source,
            sha256=sha,
            store_path=store_path,
            primary_binary=artifact.primary_binary,
            binaries=artifact.binaries,
            installed_at=_now_iso(),
        )
        payload = _read_manifest()
        existing = _find_entry(
            payload, tool=artifact.tool, version=artifact.version, sha=None
        )
        if existing is not None:
            payload["tools"][existing[0]] = _installed_to_entry(installed)
        else:
            payload["tools"].append(_installed_to_entry(installed))
        _write_manifest_atomically(payload)

        if on_line is not None:
            on_line(
                f"  ✓ Installed {artifact.tool} {artifact.version} → "
                f"{store_path}"
            )

        return InstallOutcome(
            tool=artifact.tool,
            version=artifact.version,
            sha256=sha,
            skipped=False,
            store_path=store_path,
            bytes_downloaded=bytes_downloaded,
            udev_rules_path=udev_path,
        )


# ---------------------------------------------------------------------------
# Public API: resolve / verify
# ---------------------------------------------------------------------------


def resolve(
    tool_name: str, *, version: str | None = None, sha256: str | None = None
) -> Path | None:
    """Return the absolute path to ``tool_name``'s primary binary, or
    a bundled binary if ``tool_name`` matches a bundle entry.

    Resolution order:
      1. Exact ``(tool, version, sha256)`` match — used by the build /
         flash / debug path with the project's lockfile pin.
      2. Most-recent install of that tool when only ``tool_name`` is
         given.
      3. ``None`` when nothing matches.

    Raises :class:`FamilyToolchainInstallerStoreCorruptError` when a
    manifest entry references a missing ``store/<sha>/`` directory.
    """
    payload = _read_manifest()

    def _provides(entry: dict[str, Any]) -> bool:
        if entry.get("tool") == tool_name:
            return True
        for rel in entry.get("binaries") or ():
            if not isinstance(rel, str):
                continue
            if rel == tool_name or Path(rel).name == tool_name:
                return True
        return False

    matches = [
        e for e in payload.get("tools", []) or ()
        if isinstance(e, dict) and _provides(e)
    ]
    if version is not None:
        matches = [e for e in matches if e.get("version") == version]
    if sha256 is not None:
        matches = [e for e in matches if e.get("sha256") == sha256]
    if not matches:
        return None
    # Most-recent first (descending installed_at)
    matches.sort(key=lambda e: e.get("installed_at", ""), reverse=True)
    entry = matches[0]
    store_path = Path(str(entry["store_path"]))
    if not store_path.is_dir():
        raise FamilyToolchainInstallerStoreCorruptError(
            f"manifest entry for {entry['tool']} {entry['version']} "
            f"references missing store at {store_path}.  "
            "Run `alloy toolchain install --force` to reinstall."
        )
    # If the caller asked by bundled-binary name, return the bundle path.
    if entry.get("tool") != tool_name:
        for rel in entry.get("binaries") or ():
            if Path(rel).name == tool_name or rel == tool_name:
                return store_path / rel
        return None
    return store_path / str(entry.get("primary_binary", ""))


def verify(tool_name: str, *, version: str | None = None) -> bool:
    """True iff every binary the manifest claims for ``tool_name`` exists."""
    payload = _read_manifest()
    candidates = [
        e for e in payload.get("tools", []) or () if isinstance(e, dict)
        and e.get("tool") == tool_name
        and (version is None or e.get("version") == version)
    ]
    if not candidates:
        return False
    for entry in candidates:
        store_path = Path(str(entry.get("store_path", "")))
        if not store_path.is_dir():
            return False
        for rel in entry.get("binaries") or ():
            if not (store_path / rel).exists():
                return False
    return True


# ---------------------------------------------------------------------------
# Public API: prune
# ---------------------------------------------------------------------------


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _project_pinned_shas(projects: Sequence[Path]) -> set[tuple[str, str, str]]:
    """Walk every project's ``.alloy/toolchain.lock`` and return
    the union of ``(tool, version, sha256)`` triples it pins.
    """
    pinned: set[tuple[str, str, str]] = set()
    for root in projects:
        path = root / ".alloy" / LOCKFILE_NAME
        lock: ToolchainLock | None = read_optional(path)
        if lock is None:
            continue
        for tool, pin in lock.tools.items():
            pinned.add((tool, pin.version, pin.sha256))
    return pinned


def prune(
    *, projects: Sequence[Path] = (), dry_run: bool = False
) -> PruneReport:
    """Garbage-collect store entries no project's lockfile references.

    Returns the list of candidates and (when ``dry_run=False``)
    actually deletes them.  ``projects`` is the union the caller
    supplies; pass `()` to treat every entry as prunable (the user
    really wants a wipe).
    """
    with _store_lock():
        ensure_store()
        pinned = _project_pinned_shas(projects)
        payload = _read_manifest()

        candidates: list[PruneCandidate] = []
        kept: list[dict[str, Any]] = []
        for entry in payload.get("tools", []) or ():
            if not isinstance(entry, dict):
                continue
            tool = str(entry.get("tool", ""))
            version = str(entry.get("version", ""))
            sha = str(entry.get("sha256", ""))
            store_path = Path(str(entry.get("store_path", "")))
            if (tool, version, sha) in pinned:
                kept.append(entry)
                continue
            candidates.append(
                PruneCandidate(
                    tool=tool,
                    version=version,
                    sha256=sha,
                    store_path=store_path,
                    size_bytes=_dir_size(store_path),
                )
            )

        if dry_run or not candidates:
            return PruneReport(
                candidates=tuple(candidates),
                deleted=(),
                bytes_freed=0,
                dry_run=True,
            )

        # Apply: delete store dirs + by-name entries; keep the
        # filtered manifest.
        deleted: list[PruneCandidate] = []
        bytes_freed = 0
        for cand in candidates:
            try:
                if cand.store_path.is_dir():
                    shutil.rmtree(cand.store_path, ignore_errors=True)
                _remove_by_name(cand.tool, cand.version)
            except OSError:
                continue
            deleted.append(cand)
            bytes_freed += cand.size_bytes

        payload["tools"] = kept
        _write_manifest_atomically(payload)
        return PruneReport(
            candidates=tuple(candidates),
            deleted=tuple(deleted),
            bytes_freed=bytes_freed,
            dry_run=False,
        )


def _remove_by_name(tool: str, version: str) -> None:
    target = _by_name_dir() / tool / version
    if target.is_symlink() or target.is_file():
        target.unlink(missing_ok=True)
    elif target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def installed_bin_dirs() -> list[Path]:
    """Return every ``bin/``-equivalent directory across the store.

    Used by ``alloy toolchain shell`` to augment ``PATH`` with the
    cached binaries' parent dirs.  Deduplicates by absolute path so
    a repeated install does not blow up the PATH.
    """
    seen: set[Path] = set()
    out: list[Path] = []
    for tool in list_installed():
        if not tool.store_path.is_dir():
            continue
        for rel in tool.binaries:
            bin_dir = (tool.store_path / rel).parent.resolve()
            if bin_dir in seen:
                continue
            if not bin_dir.is_dir():
                continue
            seen.add(bin_dir)
            out.append(bin_dir)
    return out


def find_installed(
    tool_name: str, *, version: str | None = None
) -> InstalledTool | None:
    """Return the first matching :class:`InstalledTool` or ``None``."""
    for tool in list_installed():
        if tool.tool != tool_name:
            continue
        if version is not None and tool.version != version:
            continue
        return tool
    return None


__all__ = [
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA_VERSION",
    "InstallOutcome",
    "InstalledTool",
    "PruneCandidate",
    "PruneReport",
    "ensure_store",
    "find_installed",
    "install",
    "installed_bin_dirs",
    "list_installed",
    "prune",
    "resolve",
    "store_root",
    "verify",
]
