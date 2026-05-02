"""Snapshot harness — pinned SVGs for every shipped TUI screen.

The SVGs under this package are the *canonical* visual goldens.
``scripts/generate_docs_images.py`` copies them into ``docs/images/``
so the public-facing gallery stays in sync.

To refresh:

    uv run pytest tests/test_snapshots.py --snapshot-update

The render helpers in :mod:`_render` build seeded apps; the
comparator in :mod:`_compare` handles the diff + update flow.
"""
