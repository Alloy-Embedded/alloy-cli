"""Shared pytest fixtures.

The ``snapshot`` marker tags pilot tests that pin a TUI screen's
visual state.  The ``snapshot_compare`` fixture exposes the
single comparison call those tests use.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add ``--snapshot-update`` so reviewers can refresh goldens.

    pytest-textual-snapshot already registers this flag for the
    syrupy comparator it ships; we re-declare it as
    ``--snapshot-refresh`` so our custom harness can branch on it
    even when the upstream flag isn't picked up by argparse first.
    """
    # Use a different option name to avoid collision with the
    # one pytest-textual-snapshot registers.  The custom flag is
    # what the assert helper reads.
    parser.addoption(
        "--snapshot-refresh",
        action="store_true",
        default=False,
        help=(
            "Rewrite the SVG goldens under tests/snapshots/ with "
            "the current render output."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "snapshot: pin a TUI screen's SVG render against tests/snapshots/.",
    )
    config.addinivalue_line(
        "markers",
        "perf: performance benchmark gated by ARCHITECTURE.md budgets.",
    )
    config.addinivalue_line(
        "markers",
        "docs: docs-site build/links/IA tests; requires `pip install -e .[docs]`.",
    )


@pytest.fixture
def snapshot_update(request: pytest.FixtureRequest) -> bool:
    """Whether the current run should rewrite golden snapshots."""
    if request.config.getoption("--snapshot-refresh", default=False):
        return True
    # Honour the upstream syrupy / pytest-textual-snapshot flag too
    # so contributors only need to remember one switch.
    return bool(request.config.getoption("--snapshot-update", default=False))


@pytest.fixture
def snapshot_compare(snapshot_update: bool):
    """Return a callable that asserts an SVG matches its golden.

    Usage::

        def test_something(snapshot_compare):
            svg = render_app(app, title="alloy 02-dashboard")
            snapshot_compare("02-dashboard", svg)
    """
    from tests.snapshots._compare import assert_svg_matches

    def _compare(name: str, svg: str) -> None:
        assert_svg_matches(name, svg, update=snapshot_update)

    return _compare
