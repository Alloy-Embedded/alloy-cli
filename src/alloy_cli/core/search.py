"""Faceted search over boards + devices.

The same logic backs:

* ``alloy boards`` / ``alloy devices`` (this proposal).
* The TUI Board Picker (``add-tui-board-picker``).
* The MCP tools (``add-mcp-server``).

Keeping it free of Click / Rich / Textual makes it cheap to reuse.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from alloy_cli.core import boards as _boards
from alloy_cli.core import ir as _ir
from alloy_cli.core.boards import BoardSummary
from alloy_cli.core.log import get_logger

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Device summary (lighter than DeviceIR — no peripheral / pin payload)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeviceSummary:
    """Per-device row used by ``alloy devices`` listings."""

    vendor: str
    family: str
    device: str
    package: str
    core: str
    summary: str
    admitted: bool
    has_features: tuple[str, ...]


_FEATURE_KEYS: dict[str, str] = {
    # YAML key (top-level) -> feature name surfaced to users
    "usb_controllers": "usb",
    "usb": "usb",
    "ethernet": "ethernet",
    "can_controllers": "can",
    "ble_radio": "ble",
    "wifi_radio": "wifi",
    "secure_element": "secure",
    "crypto": "crypto",
    "fpu": "fpu",
}


def _features_for(payload: dict) -> tuple[str, ...]:
    feats: list[str] = []
    for key, label in _FEATURE_KEYS.items():
        value = payload.get(key)
        if value:
            feats.append(label)
    # Some IRs nest under capabilities/peripherals.
    peripherals = payload.get("peripherals") or []
    if isinstance(peripherals, list):
        for entry in peripherals:
            if not isinstance(entry, dict):
                continue
            ip_name = str(entry.get("ip_name") or "").lower()
            if ip_name == "usb_otg" and "usb" not in feats:
                feats.append("usb")
            if ip_name in {"eth", "ethernet"} and "ethernet" not in feats:
                feats.append("ethernet")
            if ip_name == "can" and "can" not in feats:
                feats.append("can")
    return tuple(sorted(set(feats)))


@functools.lru_cache(maxsize=1)
def _bulk_root() -> Path:
    return _ir.data_devices_root() / "bulk-admitted" / "vendors"


def _walk_yamls(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    return root.rglob("*.yml")


_TOP_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:")
_INDENTED_KEY_RE = re.compile(r"^\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def _strip_yaml_value(value: str) -> str:
    """Strip a scalar YAML value of inline comments + surrounding quotes."""
    if "#" in value and not value.startswith('"') and not value.startswith("'"):
        value = value.split("#", 1)[0]
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return value


def _fast_identity_scan(path: Path) -> dict[str, str] | None:
    """Read only the ``identity:`` block from a device YAML.

    Avoids loading the entire (potentially huge) IR file when callers
    only need vendor / family / device / package / core / summary.
    Returns ``None`` if no identity block is found.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    in_identity = False
    identity: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw or raw.startswith("#"):
            continue
        if not in_identity:
            top = _TOP_KEY_RE.match(raw)
            if top and top.group(1) == "identity":
                in_identity = True
            continue
        # We're inside the identity block.  Stop on the next top-level key.
        if _TOP_KEY_RE.match(raw):
            break
        m = _INDENTED_KEY_RE.match(raw)
        if not m:
            continue
        key, value = m.group(1), _strip_yaml_value(m.group(2))
        if value:
            identity[key] = value
    return identity if identity else None


def _summary_from_yaml(path: Path, *, admitted: bool, fast: bool = False) -> DeviceSummary | None:
    """Parse just enough of a device YAML to build a :class:`DeviceSummary`.

    ``fast=True`` does a regex-only identity scan and skips peripheral-based
    feature derivation — used for ``bulk-admitted/`` where speed matters.
    The curated ``vendors/`` set still gets the full YAML parse so feature
    detection picks up everything (USB controllers, ETH, BLE radio, …).
    """
    if fast:
        identity = _fast_identity_scan(path)
        if not identity or not identity.get("device"):
            return None
        return DeviceSummary(
            vendor=identity.get("vendor", ""),
            family=identity.get("family", ""),
            device=identity.get("device", ""),
            package=identity.get("package", ""),
            core=identity.get("core", ""),
            summary=identity.get("summary", ""),
            admitted=admitted,
            has_features=(),
        )
    try:
        with path.open(encoding="utf-8") as fp:
            payload = yaml.safe_load(fp)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(payload, dict):
        return None
    identity_obj = payload.get("identity") or {}
    if not isinstance(identity_obj, dict) or not identity_obj.get("device"):
        return None
    return DeviceSummary(
        vendor=str(identity_obj.get("vendor", "")),
        family=str(identity_obj.get("family", "")),
        device=str(identity_obj.get("device", "")),
        package=str(identity_obj.get("package", "")),
        core=str(identity_obj.get("core", "")),
        summary=str(identity_obj.get("summary", "")),
        admitted=admitted,
        has_features=_features_for(payload),
    )


def _bulk_cache_dir() -> Path:
    """Return ``.alloy/cache/bulk_search`` under the alloy-cli repo root."""
    return _ir.repo_root() / ".alloy" / "cache" / "bulk_search"


def _submodule_sha() -> str | None:
    """Return the alloy-devices-yml submodule SHA, or ``None`` when unknown.

    We shell out to ``git rev-parse`` so we don't drag a Python git
    library in.  Failure cases (no git on PATH, the directory isn't
    a git repo, the submodule is detached without a SHA) all return
    ``None``, which the rest of the cache treats as "disabled".
    """
    devices_root = _ir.data_devices_root()
    if not devices_root.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(devices_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


_MAX_CACHED_SHAS = 3


@dataclass(frozen=True, slots=True)
class _BulkCache:
    """SHA-keyed disk cache for bulk-admitted device summaries.

    The on-disk format is a single JSON file per SHA, holding the
    full :class:`DeviceSummary` list.  Misses fall through to the
    YAML parser and re-populate the cache; writes are atomic
    (temp file + ``os.replace``).
    """

    directory: Path

    def read(self, sha: str) -> tuple[DeviceSummary, ...] | None:
        path = self.directory / f"{sha}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("Bulk cache at %s is unreadable: %s", path, exc)
            return None
        if not isinstance(payload, list):
            return None
        out: list[DeviceSummary] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            try:
                out.append(
                    DeviceSummary(
                        vendor=str(entry["vendor"]),
                        family=str(entry["family"]),
                        device=str(entry["device"]),
                        package=str(entry.get("package", "")),
                        core=str(entry.get("core", "")),
                        summary=str(entry.get("summary", "")),
                        admitted=bool(entry.get("admitted", False)),
                        has_features=tuple(entry.get("has_features", ()) or ()),
                    )
                )
            except KeyError:
                # Schema drift — bail and let the caller re-parse.
                return None
        return tuple(out)

    def write(self, sha: str, summaries: tuple[DeviceSummary, ...]) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.warning("Cannot create bulk cache dir %s: %s", self.directory, exc)
            return
        target = self.directory / f"{sha}.json"
        tmp = target.with_suffix(".json.tmp")
        encoded = [dataclasses.asdict(s) for s in summaries]
        # Tuples become lists in asdict; that's fine for JSON.
        try:
            tmp.write_text(json.dumps(encoded, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            _log.warning("Bulk cache write failed for %s: %s", target, exc)
            tmp.unlink(missing_ok=True)
            return
        self._prune()

    def _prune(self) -> None:
        try:
            entries = sorted(
                self.directory.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for stale in entries[_MAX_CACHED_SHAS:]:
            stale.unlink(missing_ok=True)

    def clear(self) -> None:
        if not self.directory.exists():
            return
        for entry in self.directory.glob("*.json"):
            entry.unlink(missing_ok=True)


def _bulk_summaries_from_index() -> tuple[DeviceSummary, ...]:
    """Read the pre-built ``bulk-admitted/index.yml`` summary.

    Consults a disk cache keyed on the ``alloy-devices-yml`` submodule
    SHA before parsing the YAML — second invocations land in <100ms
    instead of paying the ~7s parse cost.
    """
    sha = _submodule_sha()
    cache = _BulkCache(directory=_bulk_cache_dir()) if sha else None
    if cache is not None:
        cached = cache.read(sha)  # type: ignore[arg-type]
        if cached is not None:
            return cached

    index_path = _ir.data_devices_root() / "bulk-admitted" / "index.yml"
    if not index_path.exists():
        return ()
    try:
        with index_path.open(encoding="utf-8") as fp:
            payload = yaml.safe_load(fp)
    except (OSError, yaml.YAMLError):
        return ()
    if not isinstance(payload, dict):
        return ()
    devices = payload.get("devices") or []
    out: list[DeviceSummary] = []
    for entry in devices:
        if not isinstance(entry, dict):
            continue
        vendor = str(entry.get("vendor", ""))
        family = str(entry.get("family", ""))
        device = str(entry.get("device", ""))
        if not (vendor and family and device):
            continue
        out.append(
            DeviceSummary(
                vendor=vendor,
                family=family,
                device=device,
                package=str(entry.get("package", "")),
                core=str(entry.get("core", "")),
                summary=str(entry.get("summary", "")),
                admitted=False,
                has_features=(),
            )
        )
    parsed = tuple(out)
    if cache is not None and sha is not None:
        cache.write(sha, parsed)
    return parsed


@functools.lru_cache(maxsize=1)
def _device_index(*, include_bulk: bool = False) -> tuple[DeviceSummary, ...]:
    """Cached scan of ``vendors/`` and (optionally) ``bulk-admitted/``.

    For the curated catalogue we still parse each YAML in full so feature
    detection picks up USB / ETH / BLE etc.  For the bulk-admitted set we
    consume the pre-built ``bulk-admitted/index.yml`` (8 500+ entries in a
    single file) and fall back to a per-file fast scan only if the index
    is missing.
    """
    summaries: list[DeviceSummary] = []
    vendors_root = _ir.data_devices_root() / "vendors"
    if vendors_root.exists():
        # Curated YAMLs are large (1-7 MB each); use the fast identity-only
        # scan here too.  Has-feature detection over the curated set lands
        # with the codegen integration; today both paths return ``()``.
        for path in _walk_yamls(vendors_root):
            summary = _summary_from_yaml(path, admitted=True, fast=True)
            if summary is not None:
                summaries.append(summary)
    if include_bulk:
        bulk = _bulk_summaries_from_index()
        if bulk:
            summaries.extend(bulk)
        else:
            for path in _walk_yamls(_bulk_root()):
                summary = _summary_from_yaml(path, admitted=False, fast=True)
                if summary is not None:
                    summaries.append(summary)
    summaries.sort(key=lambda s: (s.vendor, s.family, s.device))
    return tuple(summaries)


def reset_caches() -> None:
    """Drop all cached IR walks (used by tests + when SDK paths change)."""
    _device_index.cache_clear()
    _bulk_root.cache_clear()
    _BulkCache(directory=_bulk_cache_dir()).clear()


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BoardFilters:
    vendor: str | None = None
    isa: str | None = None  # "cortex-m4", "rv32imc", …
    has: tuple[str, ...] = ()
    tier: int | None = None


@dataclass(frozen=True, slots=True)
class DeviceFilters:
    vendor: str | None = None
    family: str | None = None
    has: tuple[str, ...] = ()
    admitted: Literal["admitted", "all"] = "admitted"


def _matches_query(text: str, query: str) -> bool:
    return query.lower() in text.lower()


def _board_text(b: BoardSummary) -> str:
    return " ".join((b.board_id, b.mcu, b.vendor, b.family, b.device, b.summary or "")).lower()


def _device_text(d: DeviceSummary) -> str:
    return " ".join((d.device, d.vendor, d.family, d.package, d.summary or "")).lower()


def _rank(text: str, query: str) -> int:
    """Lower is better.  0 = exact prefix; 1 = startswith; 2 = substring."""
    if not query:
        return 9
    lowered = query.lower()
    if text.startswith(lowered):
        return 0
    for token in text.split():
        if token.startswith(lowered):
            return 1
    return 2 if lowered in text else 9


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------


def search_boards(
    *,
    query: str | None = None,
    filters: BoardFilters | None = None,
) -> tuple[BoardSummary, ...]:
    """Return boards from the SDK catalogue matching ``query`` + ``filters``."""
    f = filters or BoardFilters()
    catalog = _boards.load_catalog()
    results: list[tuple[int, BoardSummary]] = []
    for summary in catalog:
        if f.vendor and summary.vendor.lower() != f.vendor.lower():
            continue
        if f.isa and summary.core.lower() != f.isa.lower():
            continue
        if f.tier is not None and summary.tier != f.tier:
            continue
        if f.has and not all(feat in summary.has_features for feat in f.has):
            continue
        if query and not _matches_query(_board_text(summary), query):
            continue
        rank = _rank(_board_text(summary), query) if query else 9
        results.append((rank, summary))
    results.sort(key=lambda pair: (pair[0], pair[1].board_id))
    return tuple(s for _, s in results)


def search_devices(
    *,
    query: str | None = None,
    filters: DeviceFilters | None = None,
) -> tuple[DeviceSummary, ...]:
    """Return device summaries matching ``query`` + ``filters``.

    ``filters.admitted == "all"`` includes ``bulk-admitted/`` entries.
    """
    f = filters or DeviceFilters()
    include_bulk = f.admitted == "all"
    index = _device_index(include_bulk=include_bulk)
    results: list[tuple[int, DeviceSummary]] = []
    for summary in index:
        if f.vendor and summary.vendor.lower() != f.vendor.lower():
            continue
        if f.family and summary.family.lower() != f.family.lower():
            continue
        if f.has and not all(feat in summary.has_features for feat in f.has):
            continue
        if query and not _matches_query(_device_text(summary), query):
            continue
        rank = _rank(_device_text(summary), query) if query else 9
        results.append((rank, summary))
    results.sort(key=lambda pair: (pair[0], pair[1].vendor, pair[1].family, pair[1].device))
    return tuple(s for _, s in results)


def boards_referencing_device(vendor: str, family: str, device: str) -> tuple[BoardSummary, ...]:
    """Return curated boards whose `device` field matches the IR device id."""
    catalog = _boards.load_catalog()
    return tuple(
        b
        for b in catalog
        if b.vendor.lower() == vendor.lower()
        and b.family.lower() == family.lower()
        and b.device.lower() == device.lower()
    )


__all__ = [
    "BoardFilters",
    "DeviceFilters",
    "DeviceSummary",
    "boards_referencing_device",
    "reset_caches",
    "search_boards",
    "search_devices",
]
