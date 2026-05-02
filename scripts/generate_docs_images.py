"""Refresh the SVG documentation gallery under ``docs/images/``.

Run from the repo root:

    python scripts/generate_docs_images.py

This script is the *thin wrapper* over :mod:`tests.snapshots._render`
— the same render helpers backing the snapshot tests.  Output is
also written into ``tests/snapshots/`` so the goldens stay in sync
with the gallery byte-for-byte.

CI never runs this script — contributors run it manually after
intentionally changing a TUI screen.  The accompanying snapshot
tests are the gate that catches *unintentional* drift.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Make src/ importable when running directly out of a checkout.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ruff: noqa: E402
from tests.snapshots._compare import golden_path, write_golden
from tests.snapshots._render import (
    build_app_for,
    pinned_screen_names,
    prepare_snapshot_environment,
    render_app,
    render_cli_snippet,
)

OUT = _REPO_ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)


def _refresh_screen(name: str, *, project_root: Path) -> Path:
    app = build_app_for(name, project_root=project_root)
    svg = render_app(app, title=f"alloy {name}")
    target = write_golden(name, svg)
    shutil.copyfile(target, OUT / f"{name}.svg")
    return target


def _refresh_cli(name: str, argv: list[str]) -> Path:
    svg = render_cli_snippet(name, argv)
    target = write_golden(name, svg)
    shutil.copyfile(target, OUT / f"{name}.svg")
    return target


def main() -> None:
    project_root = _REPO_ROOT / ".tmp_screenshots"
    project_root.mkdir(parents=True, exist_ok=True)
    prepare_snapshot_environment(project_root)

    print(f"Refreshing snapshots in {golden_path('').parent.relative_to(_REPO_ROOT)} "
          f"and {OUT.relative_to(_REPO_ROOT)}")

    for name in pinned_screen_names():
        target = _refresh_screen(name, project_root=project_root)
        print(f"  ✓ {target.relative_to(_REPO_ROOT)}")

    for name, argv in (("09-cli-help", ["--help"]), ("10-cli-boards", ["boards"])):
        target = _refresh_cli(name, argv)
        print(f"  ✓ {target.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
