"""Entry point stub.  Real CLI surface is built across
``add-cli-new`` / ``add-cli-build-flash-debug`` / etc.  This module
exists so the ``alloy = "alloy_cli.main:main"`` pyproject scripts entry
resolves before any phase-2 proposal lands.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Placeholder — phase 2 ``add-cli-new`` proposal replaces this."""
    print(
        "alloy-cli: the terminal-native developer surface for the Alloy "
        "embedded platform is not yet implemented.\n"
        "See openspec/changes/ for the in-flight roadmap.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
