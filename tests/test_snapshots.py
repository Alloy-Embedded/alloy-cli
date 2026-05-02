"""Pinned-screen snapshot tests for ``add-snapshot-test-harness`` (#22).

Each pinned screen renders through :func:`tests.snapshots._render.render_app`
and is compared against the matching SVG golden under
``tests/snapshots/<name>.svg``.  Refresh with::

    uv run pytest tests/test_snapshots.py --snapshot-update

(``--snapshot-refresh`` also works.)

The tests intentionally keep the per-screen ceremony tiny — the
seeding pipeline is centralised in :mod:`tests.snapshots._render`
so the docs gallery script and these tests share one render path.
"""

from __future__ import annotations

import pytest

from tests.snapshots._render import (
    build_app_for,
    pinned_screen_names,
    prepare_snapshot_environment,
    render_app,
    render_cli_snippet,
)


@pytest.fixture(scope="module")
def seeded_root(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("alloy-snapshots")
    prepare_snapshot_environment(root)
    return root


@pytest.mark.snapshot
@pytest.mark.parametrize("name", pinned_screen_names())
def test_screen_snapshot_matches_golden(
    name: str, seeded_root, snapshot_compare
) -> None:
    app = build_app_for(name, project_root=seeded_root)
    svg = render_app(app, title=f"alloy {name}")
    snapshot_compare(name, svg)


@pytest.mark.snapshot
@pytest.mark.parametrize(
    "name,argv",
    [
        ("09-cli-help", ["--help"]),
        ("10-cli-boards", ["boards"]),
    ],
)
def test_cli_snippet_snapshot_matches_golden(
    name: str, argv: list[str], snapshot_compare
) -> None:
    svg = render_cli_snippet(name, argv)
    snapshot_compare(name, svg)
