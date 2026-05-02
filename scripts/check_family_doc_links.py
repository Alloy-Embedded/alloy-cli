"""Check that vendor `install_docs` URLs in family manifests still resolve.

Walks every ``data/families/*.yml``, collects every URL in any
``install_docs`` block, and runs a `HEAD` request against each one.
Failures are emitted as warnings — vendor URL flaps shouldn't block
unrelated PRs from merging.

Run::

    python scripts/check_family_doc_links.py            # warn-on-failure
    python scripts/check_family_doc_links.py --strict   # fail-on-failure (CI nightly)

The strict mode is meant for a separate periodic CI workflow, NOT
for the per-PR pipeline.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
FAMILIES_DIR = REPO_ROOT / "data" / "families"
TIMEOUT_S = 10


def _walk_install_docs() -> Iterator[tuple[Path, str, str, str]]:
    """Yield ``(yaml_path, tool_name, os_key, url)`` for every install_docs URL."""
    for path in sorted(FAMILIES_DIR.glob("*.yml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        for section in ("required", "recommended", "optional"):
            for entry in payload.get(section) or ():
                if not isinstance(entry, dict):
                    continue
                docs = entry.get("install_docs") or {}
                if not isinstance(docs, dict):
                    continue
                tool = str(entry.get("tool", "<unknown>"))
                for os_key, url in docs.items():
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        yield path, tool, str(os_key), url


def _check_url(url: str, *, timeout: float = TIMEOUT_S) -> tuple[bool, str]:
    """Run a HEAD request; treat 200-399 as OK.

    Many vendor sites serve 405 Method Not Allowed on HEAD; we
    fall back to GET in that case so the false-positive rate stays
    low.  Network errors return ``(False, reason)`` so the caller
    can warn.
    """
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return True, f"HEAD {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in {405, 501}:
            # Some sites disallow HEAD — try GET (no body).
            try:
                request = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(request, timeout=timeout) as resp:
                    return True, f"GET {resp.status}"
            except urllib.error.URLError as exc2:
                return False, f"GET fallback failed: {exc2}"
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"network error: {exc.reason}"
    except TimeoutError:
        return False, "timeout"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_family_doc_links.py")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on any unreachable URL (default: warn only).",
    )
    args = parser.parse_args(argv)

    failures: list[tuple[Path, str, str, str, str]] = []
    checked = 0
    for path, tool, os_key, url in _walk_install_docs():
        checked += 1
        ok, detail = _check_url(url)
        marker = "✓" if ok else "✗"
        print(
            f"{marker} {path.name} :: {tool} :: {os_key} :: {url}  [{detail}]",
            file=sys.stdout,
        )
        if not ok:
            failures.append((path, tool, os_key, url, detail))

    print(
        f"\nChecked {checked} URL(s); {len(failures)} unreachable.",
        file=sys.stdout,
    )
    if not failures:
        return 0

    print("\nUnreachable links:", file=sys.stderr)
    for path, tool, os_key, url, detail in failures:
        print(f"  • {path.name} {tool}.{os_key}: {url}  ({detail})", file=sys.stderr)

    if args.strict:
        return 1
    print(
        "\n[warning] vendor URLs flap occasionally — this run is non-fatal.\n"
        "Re-run with --strict from a nightly CI workflow if you want a hard gate.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
