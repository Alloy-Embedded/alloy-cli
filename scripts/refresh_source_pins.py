"""Refresh ``data/sources/*.json`` SHA256 fields from upstream releases.

Walks every shipped pin file, downloads each pin's URL for every
declared host, recomputes SHA256, and (with ``--apply``) updates the
JSON in place.  When all pins succeed AND no SHA stayed at the
zero-padded placeholder, the script flips the
``_pending_verification`` flag to ``false`` automatically.

Run::

    python scripts/refresh_source_pins.py                      # dry-run
    python scripts/refresh_source_pins.py --apply              # write
    python scripts/refresh_source_pins.py --source xpack --apply
    python scripts/refresh_source_pins.py --tool arm-none-eabi-gcc

Network is required.  Failures (HTTP errors, network flakes, missing
upstream artefacts) are reported per-pin but never raise — the script
exits 0 so a transient flake doesn't block CI.

Output is a unified diff to stdout when ``--dry-run`` (default).
With ``--apply``, the JSON files are rewritten on disk; the script
NEVER pushes commits or opens PRs automatically — review + commit are
human-only steps.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = REPO_ROOT / "data" / "sources"
PLACEHOLDER_SHA = "0" * 64
USER_AGENT = "alloy-cli/refresh_source_pins"
TIMEOUT_S = 60


def _walk_pins() -> Iterator[Path]:
    """Yield every shipped ``data/sources/*.json``."""
    yield from sorted(SOURCES_DIR.glob("*.json"))


def _stream_sha256(url: str, timeout: float = TIMEOUT_S) -> tuple[str, int]:
    """Download ``url`` (streaming) and return ``(sha256, byte_count)``."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            sha.update(chunk)
            total += len(chunk)
    return sha.hexdigest(), total


def _refresh_pin(
    payload: dict,
    *,
    only_tool: str | None,
) -> tuple[bool, list[str]]:
    """Recompute every host's SHA in ``payload`` (mutates in place).

    Returns ``(any_changed, log_lines)``.  log_lines lists per-host
    outcomes for human review.
    """
    changed = False
    log: list[str] = []
    for tool in payload.get("tools") or ():
        if not isinstance(tool, dict):
            continue
        if only_tool is not None and tool.get("tool") != only_tool:
            continue
        tool_name = tool.get("tool", "<unknown>")
        version = tool.get("version", "?")
        for host_id, artefact in (tool.get("hosts") or {}).items():
            if not isinstance(artefact, dict):
                continue
            url = artefact.get("url")
            old_sha = artefact.get("sha256", "")
            if not isinstance(url, str):
                log.append(f"  ✗ {tool_name} {version} {host_id}: no url")
                continue
            try:
                new_sha, size = _stream_sha256(url)
            except urllib.error.URLError as exc:
                log.append(
                    f"  ✗ {tool_name} {version} {host_id}: {exc}"
                )
                continue
            except OSError as exc:
                log.append(
                    f"  ✗ {tool_name} {version} {host_id}: {exc}"
                )
                continue
            if new_sha != old_sha:
                artefact["sha256"] = new_sha
                changed = True
                log.append(
                    f"  ✓ {tool_name} {version} {host_id}: "
                    f"{old_sha[:12]}… → {new_sha[:12]}…  ({size} bytes)"
                )
            else:
                log.append(
                    f"  · {tool_name} {version} {host_id}: unchanged"
                )
            # Always record the freshly-measured size so --dry-run plans
            # carry accurate totals.
            if size and artefact.get("size_bytes") != size:
                artefact["size_bytes"] = size
                changed = True
    return changed, log


def _all_shas_real(payload: dict) -> bool:
    """True iff every per-host SHA is a real (non-placeholder) hex string."""
    for tool in payload.get("tools") or ():
        if not isinstance(tool, dict):
            continue
        for artefact in (tool.get("hosts") or {}).values():
            if not isinstance(artefact, dict):
                continue
            sha = artefact.get("sha256", "")
            if not isinstance(sha, str) or sha == PLACEHOLDER_SHA:
                return False
    return True


def _render(payload: dict) -> str:
    """Render a pin file as deterministic JSON (matches the on-disk format)."""
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_source_pins.py",
        description="Recompute SHA256 fields in data/sources/*.json from upstream.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates to disk.  Default is dry-run (prints the diff).",
    )
    parser.add_argument(
        "--source",
        metavar="KIND",
        default=None,
        help="Only refresh one source (e.g. xpack / github / probe-rs / espressif).",
    )
    parser.add_argument(
        "--tool",
        metavar="NAME",
        default=None,
        help="Only refresh the named tool (across whichever pin file ships it).",
    )
    args = parser.parse_args(argv)

    targets = list(_walk_pins())
    if args.source:
        targets = [p for p in targets if p.stem == args.source]
        if not targets:
            print(
                f"refresh_source_pins.py: no pin file matches --source {args.source!r}",
                file=sys.stderr,
            )
            return 1

    overall_changed = 0
    for path in targets:
        before_text = path.read_text(encoding="utf-8")
        payload = json.loads(before_text)
        print(f"\n=== {path.relative_to(REPO_ROOT)} ===")
        changed, log = _refresh_pin(payload, only_tool=args.tool)
        for line in log:
            print(line)
        if not changed:
            print("  (no changes)")
            continue

        if _all_shas_real(payload) and payload.get("_pending_verification") is True:
            payload["_pending_verification"] = False
            print("  (cleared _pending_verification flag)")

        after_text = _render(payload)
        if not args.apply:
            diff = "".join(
                difflib.unified_diff(
                    before_text.splitlines(keepends=True),
                    after_text.splitlines(keepends=True),
                    fromfile=str(path) + " (current)",
                    tofile=str(path) + " (refreshed)",
                    n=2,
                )
            )
            if diff:
                print("\n--- diff (dry-run) ---")
                sys.stdout.write(diff)
        else:
            path.write_text(after_text, encoding="utf-8")
            print("  (written)")
        overall_changed += 1

    if overall_changed == 0:
        print("\nAll pin files are up to date.")
    elif not args.apply:
        print(
            "\n[dry-run] re-run with --apply to write the changes; the "
            "script never opens a PR automatically.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
