"""Static guard: bare ``except Exception`` MUST NOT resurface (#26).

Two ``# noqa: BLE001`` markers are intentional and document why
(third-party callable in core.codegen, user-registered factory in
tui.app); every other surviving bare-catch is a regression and
gets caught here.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src" / "alloy_cli"

# Files where a broad catch is documented as inherent
# third-party noise.  Adding a new entry here requires a
# matching ``# noqa: BLE001`` comment plus a defensible
# justification.
# Each value is a count.  `noqa` markers in source explain why.
_BROAD_CATCH_ALLOW_LIST = {
    "core/codegen.py": 1,  # entry.callable from a vendor adapter
    "core/toolchain_manager.py": 1,  # cleanup-on-failure hook in install pipeline
    "tui/app.py": 1,  # entry.factory registered by user code
}


def _count_broad_catches(path: Path) -> int:
    """Walk a Python file and count `except Exception` clauses."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        exc = node.type
        if exc is None:
            count += 1
            continue
        if isinstance(exc, ast.Name) and exc.id == "Exception":
            count += 1
            continue
        if isinstance(exc, ast.Tuple):
            if any(isinstance(el, ast.Name) and el.id == "Exception" for el in exc.elts):
                count += 1
    return count


def test_broad_catches_match_allow_list() -> None:
    actual: dict[str, int] = {}
    for path in sorted(_SRC.rglob("*.py")):
        broad = _count_broad_catches(path)
        if broad:
            relative = str(path.relative_to(_SRC))
            actual[relative] = broad

    assert actual == _BROAD_CATCH_ALLOW_LIST, (
        "Broad `except Exception` catches drifted from the allow-list.\n"
        f"  expected: {_BROAD_CATCH_ALLOW_LIST}\n"
        f"  actual:   {actual}\n"
        "If a new broad catch is genuinely needed, add it to the "
        "allow-list AND a `# noqa: BLE001 -- <reason>` comment."
    )
