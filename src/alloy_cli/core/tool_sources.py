"""Per-source adapters that translate a Wave-1 ``ToolRequirement``
into a concrete ``SourceArtifact`` (URL + SHA + archive_kind +
binaries[]) for the active host triple.

The module is intentionally split into two seams:

1. **Adapters** (``XpackAdapter``, ``GithubAdapter``,
   ``ProbeRsAdapter``, ``EspressifAdapter``) — pure projections of
   the pinned ``data/sources/*.json`` files.  No network, no
   filesystem outside the package data, no environment variables.
2. **Downloader** (``_RealDownloader``, ``FakeDownloader``) — the
   only network seam.  Every byte alloy-cli puts on disk during a
   toolchain install crosses one of these implementations, and
   each one streaming-verifies the SHA256 against the artefact's
   pinned value before finalising the file.

Wave 2 group 2 ships only the seams + the dispatcher.  Group 3's
``core.toolchain_manager`` orchestrates them into the actual
content-addressed store.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jsonschema import Draft202012Validator

from alloy_cli import __version__ as _alloy_cli_version
from alloy_cli.core.errors import (
    FamilyToolchainInstallerChecksumError,
    FamilyToolchainInstallerDownloadError,
    FamilyToolchainInstallerError,
    FamilyToolchainInstallerUnsupportedHostError,
    FamilyToolchainSchemaError,
)
from alloy_cli.core.toolchain_registry import ToolRequirement

SCHEMA_FILE = "source_manifest_v1.json"
SOURCES_DIRNAME = "sources"

# Known source-kind strings as they appear in pin files.  Maps to
# the adapter class and the on-disk JSON filename.  Adding a new
# adapter is one entry here + one new JSON file under data/sources/.
_SOURCE_KIND_TO_FILENAME: dict[str, str] = {
    "xpack": "xpack.json",
    "github": "github.json",
    "probe-rs": "probe-rs.json",
    "espressif": "espressif.json",
}


# ---------------------------------------------------------------------------
# Typed views
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HostTriple:
    """``(os, arch)`` identifier matching the schema's host enum.

    The composite ``str(triple)`` form (`"<os>-<arch>"`) is the key
    used inside pin files' ``hosts`` maps.
    """

    os: str  # "linux" | "macos" | "windows"
    arch: str  # "x86_64" | "arm64"

    def __str__(self) -> str:
        return f"{self.os}-{self.arch}"


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """Resolved per-host download specification for one tool.

    Wave 3's ``toolchain_manager`` consumes one of these per tool
    and feeds it through the downloader → SHA verify → extract
    pipeline.
    """

    tool: str
    version: str
    source: str  # "xpack" | "github" | "probe-rs" | "espressif"
    url: str
    sha256: str
    archive_kind: str  # "tar.xz" | "tar.gz" | "tar.bz2" | "zip" | "bin"
    extract_to_subdir: str  # "" when not declared
    binaries: tuple[str, ...]
    udev_rules: str = ""  # Linux probe rules content, "" when none
    size_bytes: int | None = None

    @property
    def host_key(self) -> str:
        """The pin file's host map key this artefact came from."""
        return ""  # adapters fill this via `_project_artefact` → SourceArtifact-with-extra

    @property
    def primary_binary(self) -> str:
        """The first declared binary path (relative to the extracted root)."""
        return self.binaries[0] if self.binaries else ""


# ---------------------------------------------------------------------------
# Source / Downloader Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class Source(Protocol):
    """Adapters honour this single-method protocol."""

    @property
    def kind(self) -> str:
        """Source kind string matching `data/sources/<kind>.json`."""
        ...

    def resolve(
        self, tool: ToolRequirement, host: HostTriple
    ) -> SourceArtifact:  # pragma: no cover — protocol declaration
        """Return the concrete artefact for ``tool`` on ``host``.

        Raises:
          FamilyToolchainInstallerUnsupportedHostError: when no pin
            exists for the requested ``(tool, host)`` combination.
        """
        ...


@runtime_checkable
class Downloader(Protocol):
    """The single network seam in alloy-cli's installer.

    Implementations stream the artefact's URL to disk while hashing
    on the wire; if the running SHA256 diverges from the pin,
    refuse to finalise the file and raise the typed checksum error.
    """

    def fetch(
        self,
        artifact: SourceArtifact,
        dest: Path,
        *,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:  # pragma: no cover — protocol declaration
        ...


# ---------------------------------------------------------------------------
# Host triple resolution
# ---------------------------------------------------------------------------


_OS_FROM_PLATFORM: dict[str, str] = {
    "Darwin": "macos",
    "Linux": "linux",
    "Windows": "windows",
}

_ARCH_FROM_MACHINE: dict[str, str] = {
    "x86_64": "x86_64",
    "AMD64": "x86_64",
    "amd64": "x86_64",
    "arm64": "arm64",
    "arm64e": "arm64",
    "aarch64": "arm64",
    "ARM64": "arm64",
}


def host_triple() -> HostTriple:
    """Return the active host triple, or raise the typed error.

    Aliases: ``AMD64`` / ``amd64`` → ``x86_64``;
    ``aarch64`` / ``arm64e`` / ``ARM64`` → ``arm64``.  Anything else
    surfaces as ``family-toolchain-installer-unsupported-host``
    with the actual ``platform.system()`` / ``platform.machine()``
    pair in the message.
    """
    sysname = platform.system()
    machine = platform.machine()

    os_id = _OS_FROM_PLATFORM.get(sysname)
    arch_id = _ARCH_FROM_MACHINE.get(machine)
    if os_id is None or arch_id is None:
        raise FamilyToolchainInstallerUnsupportedHostError(
            f"Unsupported host: platform.system()={sysname!r}, "
            f"platform.machine()={machine!r}.  Supported triples: "
            "linux/macos/windows x x86_64/arm64."
        )
    return HostTriple(os=os_id, arch=arch_id)


# ---------------------------------------------------------------------------
# Schema loader + pin loader (mirrors core.toolchain_registry pattern)
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _repo_schema_path() -> Path:
    return _REPO_ROOT / "schema" / SCHEMA_FILE


def _repo_sources_dir() -> Path:
    return _REPO_ROOT / "data" / SOURCES_DIRNAME


def _repo_pin_path(filename: str) -> Path:
    return _repo_sources_dir() / filename


def _load_schema_dict() -> dict[str, Any]:
    """Load the source-manifest JSON Schema (repo path → wheel data)."""
    repo_path = _repo_schema_path()
    if repo_path.exists():
        return json.loads(repo_path.read_text(encoding="utf-8"))
    try:
        with (
            resources.files("alloy_cli")
            .joinpath(f"schema/{SCHEMA_FILE}")
            .open("r", encoding="utf-8") as fp
        ):
            return json.load(fp)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise FamilyToolchainSchemaError(
            f"source-manifest schema {SCHEMA_FILE!r} not found.  "
            "Reinstall alloy-cli or check the development checkout."
        ) from exc


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = _load_schema_dict()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _read_pin_text(filename: str) -> str:
    """Return the raw JSON text for a pin file (repo → wheel)."""
    repo_path = _repo_pin_path(filename)
    if repo_path.exists():
        return repo_path.read_text(encoding="utf-8")
    try:
        with (
            resources.files("alloy_cli")
            .joinpath(f"data/{SOURCES_DIRNAME}/{filename}")
            .open("r", encoding="utf-8") as fp
        ):
            return fp.read()
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise FamilyToolchainSchemaError(
            f"Source pin file {filename!r} not found under "
            "data/sources/.  Reinstall alloy-cli or check the "
            "development checkout."
        ) from exc


@lru_cache(maxsize=8)
def _load_pins(source_kind: str) -> dict[str, Any]:
    """Read + validate the pin file for ``source_kind``.

    Cached per-process — the JSON is small and never changes
    between calls within a single alloy-cli invocation.

    Raises:
      FamilyToolchainSchemaError when the file is missing or
        fails JSON-Schema validation; the message names the
        offending field path so contributors can fix it locally.
    """
    filename = _SOURCE_KIND_TO_FILENAME.get(source_kind)
    if filename is None:
        raise FamilyToolchainInstallerError(
            f"Unknown source kind {source_kind!r}.  Known: "
            f"{', '.join(sorted(_SOURCE_KIND_TO_FILENAME))}."
        )
    text = _read_pin_text(filename)
    payload = json.loads(text)
    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        details = "\n".join(
            f"  • /{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise FamilyToolchainSchemaError(
            f"data/sources/{filename} failed source-manifest schema "
            f"validation:\n{details}"
        )
    return payload


# ---------------------------------------------------------------------------
# Adapter base + concrete adapters
# ---------------------------------------------------------------------------


def _project_artefact(
    *,
    source: str,
    tool: str,
    version: str,
    host_payload: dict[str, Any],
    udev_rules: str = "",
) -> SourceArtifact:
    return SourceArtifact(
        tool=tool,
        version=version,
        source=source,
        url=str(host_payload["url"]),
        sha256=str(host_payload["sha256"]),
        archive_kind=str(host_payload["archive_kind"]),
        extract_to_subdir=str(host_payload.get("extract_to_subdir") or ""),
        binaries=tuple(host_payload.get("binaries") or ()),
        udev_rules=udev_rules,
        size_bytes=host_payload.get("size_bytes"),
    )


class _BaseAdapter:
    """Shared resolve() logic.

    Concrete adapters set ``KIND`` (matches the pin file's
    ``source`` field) and inherit the lookup machinery.
    """

    KIND: str = ""

    @property
    def kind(self) -> str:
        return self.KIND

    def _payload(self) -> dict[str, Any]:
        return _load_pins(self.KIND)

    def resolve(self, tool: ToolRequirement, host: HostTriple) -> SourceArtifact:
        payload = self._payload()
        matches = [t for t in payload.get("tools", []) if t.get("tool") == tool.tool]
        if not matches:
            raise FamilyToolchainInstallerUnsupportedHostError(
                f"{self.KIND}: no pin for tool {tool.tool!r}.  "
                "Add it to data/sources/"
                f"{_SOURCE_KIND_TO_FILENAME.get(self.KIND, '<unknown>')}."
            )
        # Wave 2 keeps it simple: when multiple versions are pinned
        # for the same tool, prefer the highest by string sort.  A
        # later wave can add proper SemVer-range matching against
        # `tool.version`.
        pin = max(matches, key=lambda t: str(t.get("version", "")))
        host_key = str(host)
        hosts = pin.get("hosts") or {}
        host_payload = hosts.get(host_key)
        if host_payload is None:
            unsupported = pin.get("unsupported_hosts") or ()
            supported = sorted(hosts.keys())
            if host_key in unsupported:
                raise FamilyToolchainInstallerUnsupportedHostError(
                    f"{self.KIND}: {tool.tool} {pin.get('version')} "
                    f"is not published for {host_key} (declared in "
                    f"unsupported_hosts).  Supported: "
                    f"{', '.join(supported) or '(none)'}."
                )
            raise FamilyToolchainInstallerUnsupportedHostError(
                f"{self.KIND}: {tool.tool} {pin.get('version')} has "
                f"no pin for {host_key}.  Supported: "
                f"{', '.join(supported) or '(none)'}."
            )
        return _project_artefact(
            source=self.KIND,
            tool=tool.tool,
            version=str(pin["version"]),
            host_payload=host_payload,
            udev_rules=str(pin.get("udev_rules") or ""),
        )


class XpackAdapter(_BaseAdapter):
    """Resolves tools published by the xPack Binary Distribution
    (https://github.com/xpack-dev-tools/...).
    """

    KIND = "xpack"


class GithubAdapter(_BaseAdapter):
    """Resolves tools published as GitHub release assets.

    Matches manifest sources of the form ``github:<owner>/<repo>``;
    the dispatcher routes every such source to this single
    adapter, which looks up by tool name in ``data/sources/github.json``.
    """

    KIND = "github"


class ProbeRsAdapter(_BaseAdapter):
    """Resolves probe-rs releases.

    Manifest source string is the literal ``probe-rs-installer``;
    the underlying pin file lives at
    ``data/sources/probe-rs.json``.
    """

    KIND = "probe-rs"


class EspressifAdapter(_BaseAdapter):
    """Resolves Espressif-published tools (Xtensa + RISC-V GCC bundles)."""

    KIND = "espressif"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def adapter_for(source: str) -> Source:
    """Return the adapter responsible for ``source``.

    ``source`` is the manifest's ``source`` field as authored in
    a family manifest.  Mapping:

    | manifest source              | adapter            |
    |------------------------------|--------------------|
    | ``xpack``                    | XpackAdapter       |
    | ``github:<owner>/<repo>``    | GithubAdapter      |
    | ``probe-rs-installer``       | ProbeRsAdapter     |
    | ``espressif``                | EspressifAdapter   |
    | ``vendor``                   | (raises)           |

    Vendor-source tools are EULA-gated; this dispatcher refuses to
    return an adapter for them so callers cannot accidentally
    auto-install a tool the legal contract requires the user to
    fetch manually.

    Raises:
      FamilyToolchainInstallerUnsupportedHostError: when ``source``
        is ``"vendor"``.
      FamilyToolchainInstallerError: when ``source`` is unrecognised.
    """
    if source == "vendor":
        raise FamilyToolchainInstallerUnsupportedHostError(
            "vendor-source tools are EULA-gated and install manually; "
            "no automatic adapter is available."
        )
    if source == "xpack":
        return XpackAdapter()
    if source == "probe-rs-installer":
        return ProbeRsAdapter()
    if source == "espressif":
        return EspressifAdapter()
    if source.startswith("github:"):
        return GithubAdapter()
    raise FamilyToolchainInstallerError(
        f"Unknown manifest source string {source!r}.  Recognised "
        "prefixes: xpack | github:<owner>/<repo> | probe-rs-installer "
        "| espressif | vendor."
    )


# ---------------------------------------------------------------------------
# Downloader implementations
# ---------------------------------------------------------------------------


_USER_AGENT = f"alloy-cli/{_alloy_cli_version} (toolchain-installer)"
_CHUNK = 1 << 16  # 64 KiB
_RETRY_BACKOFF_S = 1.5


def _streaming_sha256(stream: Any, dest: Path, *, expected: str,
                      on_progress: Callable[[int, int | None], None] | None,
                      total: int | None) -> Path:
    """Stream ``stream`` to ``dest.with_suffix(.partial)``, hash on the wire,
    and atomically promote on SHA match.

    Refuses to rename the partial file when the running SHA diverges
    from ``expected`` — so a tampered tarball never lands at ``dest``.
    """
    partial = dest.with_suffix(dest.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    written = 0
    try:
        with partial.open("wb") as fp:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                sha.update(chunk)
                fp.write(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(written, total)
        actual = sha.hexdigest()
        if actual != expected.lower():
            raise FamilyToolchainInstallerChecksumError(
                f"SHA256 mismatch for {dest.name}: expected "
                f"{expected[:16]}…, got {actual[:16]}…"
            )
        partial.replace(dest)
    except FamilyToolchainInstallerChecksumError:
        # Best-effort cleanup; a stale partial gets swept on the next
        # install pass anyway, so we don't surface cleanup errors.
        partial.unlink(missing_ok=True)
        raise
    except OSError:
        partial.unlink(missing_ok=True)
        raise
    return dest


class _RealDownloader:
    """Production :class:`Downloader` — uses stdlib ``urllib.request``."""

    def fetch(
        self,
        artifact: SourceArtifact,
        dest: Path,
        *,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        request = urllib.request.Request(
            artifact.url,
            headers={"User-Agent": _USER_AGENT},
        )
        last_error: Exception | None = None
        for attempt in range(2):  # one retry with backoff
            try:
                with urllib.request.urlopen(request, timeout=60) as resp:
                    total_str = resp.headers.get("Content-Length")
                    total = int(total_str) if total_str and total_str.isdigit() else None
                    return _streaming_sha256(
                        resp,
                        dest,
                        expected=artifact.sha256,
                        on_progress=on_progress,
                        total=total,
                    )
            except FamilyToolchainInstallerChecksumError:
                # Don't retry a checksum mismatch — the artefact is bad.
                raise
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(_RETRY_BACKOFF_S)
                    continue
                break
        raise FamilyToolchainInstallerDownloadError(
            f"Download failed for {artifact.url}: {last_error}"
        )


@dataclass
class FakeDownloader:
    """Test seam: copies a fixture file from ``fixtures[url]`` into ``dest``.

    The fake still exercises the streaming-SHA path so tests can
    verify both the success branch (SHA matches the pin) and the
    failure branch (pre-corrupted fixture → checksum error).
    """

    fixtures: dict[str, Path] = field(default_factory=dict)
    calls: list[SourceArtifact] = field(default_factory=list)

    def expect(self, url: str, src: Path) -> None:
        """Register a fixture for a URL."""
        self.fixtures[url] = src

    def fetch(
        self,
        artifact: SourceArtifact,
        dest: Path,
        *,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        self.calls.append(artifact)
        src = self.fixtures.get(artifact.url)
        if src is None:
            raise FamilyToolchainInstallerDownloadError(
                f"FakeDownloader: no fixture for {artifact.url}.  "
                "Register one via FakeDownloader.expect(url, path)."
            )
        # Copy via stream so the SHA path is exercised honestly.
        with src.open("rb") as fp:
            return _streaming_sha256(
                fp,
                dest,
                expected=artifact.sha256,
                on_progress=on_progress,
                total=src.stat().st_size,
            )


# Module-level singleton so callers can swap with FakeDownloader in tests.
downloader: Downloader = _RealDownloader()


def configure_downloader(new_downloader: Downloader) -> Callable[[], None]:
    """Swap the module-level downloader; returns a function that restores it.

    Mirrors ``core.process.configure(...)``.
    """
    global downloader
    previous = downloader
    downloader = new_downloader

    def _restore() -> None:
        global downloader
        downloader = previous

    return _restore


# ---------------------------------------------------------------------------
# Helpers for inspection (used by `alloy toolchain list/install --dry-run`)
# ---------------------------------------------------------------------------


def known_source_kinds() -> tuple[str, ...]:
    """Return every source-kind alloy-cli ships a pin file for."""
    return tuple(sorted(_SOURCE_KIND_TO_FILENAME))


def file_sha256(path: Path) -> str:
    """Compute the SHA256 of a file on disk (used by tests + the
    refresh-pins script).  Streams the file to avoid loading large
    tarballs into memory.
    """
    sha = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(_CHUNK), b""):
            sha.update(chunk)
    return sha.hexdigest()


# Public API
__all__ = [
    "SCHEMA_FILE",
    "SOURCES_DIRNAME",
    "Downloader",
    "EspressifAdapter",
    "FakeDownloader",
    "GithubAdapter",
    "HostTriple",
    "ProbeRsAdapter",
    "Source",
    "SourceArtifact",
    "XpackAdapter",
    "adapter_for",
    "configure_downloader",
    "downloader",
    "file_sha256",
    "host_triple",
    "known_source_kinds",
]


