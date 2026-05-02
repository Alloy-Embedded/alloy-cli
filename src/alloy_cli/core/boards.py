"""Board catalogue loader.

Reads ``board.json`` files from the resolved alloy SDK checkout
and exposes typed views.  In Phase 1 (this proposal) the catalogue
is read from a configurable directory pointed at by the
``ALLOY_BOARDS_ROOT`` env var or, by default, an empty catalogue
(downstream proposal ``add-cli-new`` wires the SDK download path).

Tests can point ``ALLOY_BOARDS_ROOT`` at a fixtures directory
containing real ``board.json`` files.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from alloy_cli.core.errors import BoardNotFoundError


@dataclass(frozen=True, slots=True)
class BoardSummary:
    """Summary card used by ``alloy boards`` listings."""

    board_id: str
    vendor: str
    family: str
    device: str
    mcu: str
    core: str
    flash_size_bytes: int
    clock_profiles: tuple[str, ...]
    tier: int
    has_features: tuple[str, ...]
    summary: str | None


@dataclass(frozen=True, slots=True)
class BoardManifest:
    """Full board manifest as decoded from ``board.json``.

    The raw JSON is exposed for fields we haven't yet typed.
    """

    board_id: str
    vendor: str
    family: str
    device: str
    arch: str
    mcu: str
    flash_size_bytes: int
    summary: BoardSummary
    payload: dict[str, Any] = field(repr=False)


def _boards_root() -> Path | None:
    raw = os.environ.get("ALLOY_BOARDS_ROOT")
    if raw:
        path = Path(raw)
        if path.exists():
            return path
    return None


def _has_features(payload: dict[str, Any]) -> tuple[str, ...]:
    feats: list[str] = []
    if payload.get("leds"):
        feats.append("led")
    if payload.get("buttons"):
        feats.append("button")
    if payload.get("uart", {}).get("debug"):
        feats.append("debug-uart")
    if payload.get("usb"):
        feats.append("usb")
    if payload.get("ethernet"):
        feats.append("ethernet")
    if payload.get("ble"):
        feats.append("ble")
    if payload.get("wifi"):
        feats.append("wifi")
    if payload.get("can"):
        feats.append("can")
    if payload.get("mcuboot"):
        feats.append("mcuboot")
    return tuple(feats)


def _decode_manifest(path: Path) -> BoardManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = BoardSummary(
        board_id=str(payload.get("board_id", path.parent.name)),
        vendor=str(payload.get("vendor", "")),
        family=str(payload.get("family", "")),
        device=str(payload.get("device", "")),
        mcu=str(payload.get("mcu", "")),
        core=str(payload.get("arch", payload.get("core", ""))),
        flash_size_bytes=int(payload.get("flash_size_bytes", 0)),
        clock_profiles=tuple(payload.get("clock_profiles", []) or ()),
        tier=int(payload.get("tier", 99)),
        has_features=_has_features(payload),
        summary=payload.get("summary"),
    )
    return BoardManifest(
        board_id=summary.board_id,
        vendor=summary.vendor,
        family=summary.family,
        device=summary.device,
        arch=str(payload.get("arch", "")),
        mcu=summary.mcu,
        flash_size_bytes=summary.flash_size_bytes,
        summary=summary,
        payload=payload,
    )


@lru_cache(maxsize=1)
def load_catalog() -> tuple[BoardSummary, ...]:
    """Walk every ``<root>/<board>/board.json`` and return a stable list.

    Returns an empty tuple when ``ALLOY_BOARDS_ROOT`` is unset or
    points at a non-existent directory.
    """
    root = _boards_root()
    if root is None:
        return ()
    summaries: list[BoardSummary] = []
    for board_dir in sorted(root.iterdir()):
        if not board_dir.is_dir():
            continue
        manifest_path = board_dir / "board.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = _decode_manifest(manifest_path)
        except (json.JSONDecodeError, ValueError):
            continue
        summaries.append(manifest.summary)
    return tuple(summaries)


def lookup(board_id: str) -> BoardManifest:
    """Return the full manifest for a board, by id."""
    root = _boards_root()
    if root is None:
        raise BoardNotFoundError(
            "Board catalogue is empty.  Set ALLOY_BOARDS_ROOT or run "
            "`alloy sdk install` (subsequent proposal) to populate one."
        )
    manifest_path = root / board_id / "board.json"
    if not manifest_path.exists():
        raise BoardNotFoundError(f"Board {board_id!r} not found at {manifest_path}.")
    return _decode_manifest(manifest_path)


__all__ = [
    "BoardManifest",
    "BoardSummary",
    "load_catalog",
    "lookup",
]
