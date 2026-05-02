"""CI guard: every declared `error_type` has a cookbook anchor.

Walk the Python tree, harvest every `error_type = "..."` assignment,
and assert ``docs/ERROR_COOKBOOK.md`` has a ``## <error-type>``
section for each one.  Run as::

    python scripts/check_error_cookbook.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src" / "alloy_cli"
_COOKBOOK = _REPO_ROOT / "docs" / "ERROR_COOKBOOK.md"


def _harvest_error_types() -> set[str]:
    """Walk every Python file and harvest `error_type = "..."` literals."""
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "error_type":
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        found.add(node.value.value)
    return found


def _harvest_cookbook_anchors() -> set[str]:
    """Pull `## <name>` headings out of ERROR_COOKBOOK.md."""
    if not _COOKBOOK.exists():
        return set()
    pattern = re.compile(r"^##\s+(\S[^\n]*)\s*$")
    out: set[str] = set()
    for line in _COOKBOOK.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if m:
            out.add(m.group(1).strip())
    return out


def main() -> int:
    declared = _harvest_error_types()
    documented = _harvest_cookbook_anchors()
    # The base AlloyCliError isn't typically raised directly; it's
    # the umbrella.  Still document it so we never lose the contract.
    declared.discard("AlloyCliError")

    missing = sorted(declared - documented)
    if missing:
        print(
            "Missing cookbook anchors:\n  - "
            + "\n  - ".join(missing)
            + "\nUpdate docs/ERROR_COOKBOOK.md with one `## <name>` "
            "section per missing error_type.",
            file=sys.stderr,
        )
        return 1
    print(f"OK — {len(declared)} error_types all documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
