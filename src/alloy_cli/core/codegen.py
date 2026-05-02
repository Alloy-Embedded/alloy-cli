"""alloy-codegen integration — runs ahead of cmake to (re)generate headers.

The codegen pass is keyed on a per-device stamp under
``.alloy/generated/<device>/.stamp``: invalidated by the IR file's
SHA, the alloy-codegen pinned version, and the alloy-cli version.

When the ``alloy_codegen`` package is not importable in the active
Python environment, the discovery helpers return ``None`` and
:func:`regenerate_if_stale` skips the step with a warning so the
build pipeline keeps working in CI containers without the codegen
dep installed.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alloy_cli import __version__ as _alloy_cli_version
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.ir import device_yaml_path
from alloy_cli.core.project import AlloyDir, ProjectConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class CodegenError(AlloyCliError):
    error_type = "codegen-error"


@dataclass(frozen=True, slots=True)
class CodegenEntry:
    """Discovered ``alloy_codegen`` entry point."""

    version: str
    callable: Callable[[ProjectConfig, Path], Any]


@dataclass(frozen=True, slots=True)
class RegenResult:
    """Outcome of a codegen pass."""

    returncode: int | None
    skipped: bool
    out_dir: Path
    written: tuple[Path, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class _Stamp:
    """Persisted cache key.  Stored as JSON next to the generated tree."""

    ir_sha: str
    codegen_version: str
    alloy_cli_version: str
    generated_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "ir_sha": self.ir_sha,
                "codegen_version": self.codegen_version,
                "alloy_cli_version": self.alloy_cli_version,
                "generated_at": self.generated_at,
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text: str) -> _Stamp | None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        try:
            return cls(
                ir_sha=str(payload["ir_sha"]),
                codegen_version=str(payload["codegen_version"]),
                alloy_cli_version=str(payload["alloy_cli_version"]),
                generated_at=str(payload.get("generated_at", "")),
            )
        except KeyError:
            return None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_codegen_entry() -> CodegenEntry | None:
    """Probe ``alloy_codegen`` for a ``generate`` callable.

    Returns ``None`` (with a warning logged) when the package is
    missing, has no ``generate`` attribute, or fails to expose a
    version string.  Callers treat this as "skip the step".
    """
    try:
        module = importlib.import_module("alloy_codegen")
    except Exception:
        logger.debug("alloy_codegen is not importable; codegen will be skipped.")
        return None
    callable_obj = getattr(module, "generate", None)
    if not callable(callable_obj):
        logger.warning("alloy_codegen is installed but has no `generate` callable.")
        return None
    version = str(getattr(module, "__version__", "0.0.0"))
    return CodegenEntry(version=version, callable=callable_obj)


# ---------------------------------------------------------------------------
# Stamp helpers
# ---------------------------------------------------------------------------


def _device_label(config: ProjectConfig) -> str:
    if config.chip is not None:
        return f"{config.chip.vendor}_{config.chip.family}_{config.chip.device}"
    if config.board is not None:
        return f"board_{config.board.id}"
    return "unknown"


def _ir_sha(config: ProjectConfig) -> str:
    """SHA-256 of the device IR YAML (or "" when no chip is pinned)."""
    if config.chip is None:
        return ""
    path = device_yaml_path(
        vendor=config.chip.vendor,
        family=config.chip.family,
        device=config.chip.device,
    )
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _stamp_path(layout: AlloyDir, device_label: str) -> Path:
    return layout.generated / device_label / ".stamp"


def _read_stamp(path: Path) -> _Stamp | None:
    if not path.exists():
        return None
    try:
        return _Stamp.from_json(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _expected_stamp(config: ProjectConfig, codegen_version: str) -> _Stamp:
    return _Stamp(
        ir_sha=_ir_sha(config),
        codegen_version=codegen_version,
        alloy_cli_version=_alloy_cli_version,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def _stamp_is_fresh(actual: _Stamp | None, expected: _Stamp) -> bool:
    if actual is None:
        return False
    return (
        actual.ir_sha == expected.ir_sha
        and actual.codegen_version == expected.codegen_version
        and actual.alloy_cli_version == expected.alloy_cli_version
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def regenerate_if_stale(
    config: ProjectConfig,
    layout: AlloyDir,
    *,
    entry: CodegenEntry | None = None,
    on_line: Callable[[str], None] | None = None,
) -> RegenResult:
    """Run codegen iff the stamp is missing / stale.

    ``entry`` defaults to :func:`discover_codegen_entry` when None.
    Returns a :class:`RegenResult`; ``returncode=None`` means the
    step was skipped because alloy-codegen isn't installed.
    """
    entry = entry if entry is not None else discover_codegen_entry()
    device_label = _device_label(config)
    out_dir = layout.generated / device_label

    if entry is None:
        if on_line is not None:
            on_line("[codegen] alloy-codegen is not installed; skipping regeneration.")
        return RegenResult(
            returncode=None,
            skipped=True,
            out_dir=out_dir,
            reason="alloy-codegen-not-installed",
        )

    expected = _expected_stamp(config, entry.version)
    actual = _read_stamp(_stamp_path(layout, device_label))
    if _stamp_is_fresh(actual, expected):
        if on_line is not None:
            on_line(f"[codegen] stamp fresh for {device_label}; skipping.")
        return RegenResult(returncode=0, skipped=True, out_dir=out_dir, reason="stamp-fresh")

    return _run_entry(entry, config, layout, expected, on_line=on_line)


def force_regenerate(
    config: ProjectConfig,
    layout: AlloyDir,
    *,
    entry: CodegenEntry | None = None,
    on_line: Callable[[str], None] | None = None,
) -> RegenResult:
    """Run codegen unconditionally.

    Used by ``alloy build --regen`` and the ``alloy.regenerate`` MCP
    tool.  Refuses (raises :class:`CodegenError`) when alloy-codegen
    isn't installed — callers requested an explicit run.
    """
    entry = entry if entry is not None else discover_codegen_entry()
    if entry is None:
        raise CodegenError(
            "alloy-codegen is not installed.  `pip install alloy-codegen` (or "
            "`pip install alloy-cli[codegen]` once that extra exists)."
        )
    expected = _expected_stamp(config, entry.version)
    return _run_entry(entry, config, layout, expected, on_line=on_line)


def _run_entry(
    entry: CodegenEntry,
    config: ProjectConfig,
    layout: AlloyDir,
    expected: _Stamp,
    *,
    on_line: Callable[[str], None] | None,
) -> RegenResult:
    device_label = _device_label(config)
    out_dir = layout.generated / device_label
    out_dir.mkdir(parents=True, exist_ok=True)

    if on_line is not None:
        on_line(f"[codegen] regenerating {device_label} via alloy-codegen {entry.version}")

    written_before = _snapshot_files(out_dir)
    try:
        entry.callable(config, out_dir)
    except Exception as exc:
        if on_line is not None:
            on_line(f"[codegen] failed: {exc}")
        return RegenResult(
            returncode=1,
            skipped=False,
            out_dir=out_dir,
            written=(),
            reason=f"codegen-error: {exc}",
        )
    written_after = _snapshot_files(out_dir)
    new_files = tuple(sorted(written_after - written_before))

    stamp_path = _stamp_path(layout, device_label)
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(expected.to_json(), encoding="utf-8")

    return RegenResult(
        returncode=0,
        skipped=False,
        out_dir=out_dir,
        written=new_files,
        reason="generated",
    )


def _snapshot_files(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {p for p in root.rglob("*") if p.is_file()}


__all__ = [
    "CodegenEntry",
    "CodegenError",
    "RegenResult",
    "discover_codegen_entry",
    "force_regenerate",
    "regenerate_if_stale",
]
