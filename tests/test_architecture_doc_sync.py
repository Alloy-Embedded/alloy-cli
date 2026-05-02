"""Docs-sync: ARCHITECTURE.md performance table mirrors _budgets.py.

Without this guard a contributor could update one and forget the
other, breaking the "the table is the contract" promise.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.perf._budgets import BUDGETS_SECONDS

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARCH = _REPO_ROOT / "docs" / "ARCHITECTURE.md"


def _parse_arch_budgets() -> dict[str, float]:
    """Read the perf table out of ARCHITECTURE.md.

    Rows look like::

        | `alloy --help` | < 80 ms |
        | `alloy build` overhead | < 50 ms over raw cmake |

    We strip backticks + leading/trailing whitespace from the
    full label cell and convert the threshold to seconds.
    """
    out: dict[str, float] = {}
    row = re.compile(
        r"\|\s*(?P<label>[^|]+?)\s*\|\s*<\s*(?P<value>[\d.]+)\s*(?P<unit>ms|s)\b",
    )
    for raw in _ARCH.read_text(encoding="utf-8").splitlines():
        m = row.search(raw)
        if not m:
            continue
        label = m["label"].replace("`", "").strip()
        # Drop parenthetical qualifiers like "(cached)".
        label = re.sub(r"\s*\([^)]*\)", "", label).strip()
        if not label:
            continue
        seconds = float(m["value"]) / 1000.0 if m["unit"] == "ms" else float(m["value"])
        out[label] = seconds
    return out


def test_architecture_md_table_matches_budgets_py() -> None:
    arch = _parse_arch_budgets()
    # Every Python budget MUST appear in the doc table.
    for label, budget in BUDGETS_SECONDS.items():
        assert label in arch, (
            f"_budgets.py declares {label!r} but docs/ARCHITECTURE.md "
            f"has no matching row.  Update both."
        )
        assert abs(arch[label] - budget) < 1e-9, (
            f"Budget mismatch for {label!r}: "
            f"docs/ARCHITECTURE.md = {arch[label]}s, "
            f"_budgets.py = {budget}s"
        )
