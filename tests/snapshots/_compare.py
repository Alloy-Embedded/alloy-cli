"""SVG snapshot comparison harness.

Used by ``tests/test_snapshots.py``.  Keeps the comparison logic
out of pytest-textual-snapshot's specific shape so we can store
goldens directly under ``tests/snapshots/<name>.svg`` and copy
them verbatim into ``docs/images/`` from the gallery script.
"""

from __future__ import annotations

import re
from pathlib import Path

_SNAPSHOT_DIR = Path(__file__).resolve().parent

# Strip the random-id chrome rich.Console.export_svg() injects so
# two renders of the same screen are byte-stable.
_TERMINAL_ID_RE = re.compile(r"\bterminal-\d+-([\w-]+)")
_DEF_PREFIX_RE = re.compile(r"<style>([^<]*)\.terminal-\d+-")


def normalize(svg: str) -> str:
    """Drop the random ids so equality comparison is deterministic."""
    out = _TERMINAL_ID_RE.sub(r"terminal-\1", svg)
    out = _DEF_PREFIX_RE.sub(lambda m: f"<style>{m.group(1)}.terminal-", out)
    return out


def golden_path(name: str) -> Path:
    """Return the on-disk location of one named golden."""
    return _SNAPSHOT_DIR / f"{name}.svg"


def read_golden(name: str) -> str | None:
    path = golden_path(name)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_golden(name: str, svg: str) -> Path:
    path = golden_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return path


def assert_svg_matches(name: str, actual_svg: str, *, update: bool) -> None:
    """Compare ``actual_svg`` to the on-disk golden.

    When ``update`` is True the golden is rewritten and the
    function returns silently.  Otherwise a missing golden raises
    ``AssertionError`` with the refresh hint, and a mismatch
    raises ``AssertionError`` showing the first diff line.
    """
    actual = normalize(actual_svg)
    if update:
        write_golden(name, actual)
        return

    expected = read_golden(name)
    if expected is None:
        raise AssertionError(
            f"Missing snapshot golden for {name!r}.\n"
            f"Re-run with `pytest --snapshot-update` to create "
            f"{golden_path(name).relative_to(_SNAPSHOT_DIR.parents[1])}."
        )

    expected_norm = normalize(expected)
    if expected_norm == actual:
        return

    # Find the first differing chunk for the error message — full
    # SVG diffs are huge, so we point reviewers at git diff.
    relpath = golden_path(name).relative_to(_SNAPSHOT_DIR.parents[1])
    raise AssertionError(
        f"Snapshot mismatch for {name!r}.\n"
        f"  golden: {relpath}\n"
        f"  refresh: pytest --snapshot-update tests/test_snapshots.py\n"
        f"  inspect: git diff {relpath}"
    )


__all__ = [
    "assert_svg_matches",
    "golden_path",
    "normalize",
    "read_golden",
    "write_golden",
]
