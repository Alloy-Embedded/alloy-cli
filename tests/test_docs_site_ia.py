"""Regression guard: the IA tree contains every required section
and every existing `docs/*.md` is reachable.

Parses `mkdocs.yml` directly (no MkDocs CLI required, so this test
runs even when the `[docs]` extras aren't installed) and asserts:

  * Top-level nav contains every section listed in the IA spec
    (Home / Getting Started / User Guide / Reference / Concepts /
    Architecture & Design / Contributing / API Reference).
  * Every `docs/*.md` file is reachable via the nav OR is listed
    in the `not_in_nav:` exemption block OR is registered in the
    `mkdocs-redirects` `redirect_maps`.
  * Every redirect target is itself a real file under `docs/`.

Unlike the build / link tests, this one runs without mkdocs
installed.  It's a structural invariant test — no file rendering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# yaml ships with MkDocs but is also a common dep — it's available
# anywhere.  If it isn't, we surface a SKIP rather than fail.
yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"
DOCS_DIR = REPO_ROOT / "docs"


# Top-level sections every release of the docs site MUST have.
# (See `add-docs-site` proposal IA spec.)
_REQUIRED_TOP_LEVEL_SECTIONS: tuple[str, ...] = (
    "Home",
    "Getting Started",
    "User Guide",
    "Reference",
    "Concepts",
    "Architecture & Design",
    "Contributing",
    "API Reference",
)


def _load_mkdocs_yml() -> dict:
    """MkDocs YAML uses `!!python/name:...` tags — load with a
    permissive loader (UnsafeLoader) since we control the file."""
    return yaml.load(MKDOCS_YML.read_text(encoding="utf-8"), Loader=yaml.UnsafeLoader)


def _flatten_nav(nav: list, prefix: str = "") -> list[tuple[str, str]]:
    """Walk the nav tree, return ``[(section_path, doc_path), ...]``.

    Skips nodes whose value is a sub-list (those are sections, not
    pages) — but recurses into them.
    """
    out: list[tuple[str, str]] = []
    for entry in nav:
        if not isinstance(entry, dict):
            continue
        for label, value in entry.items():
            section = f"{prefix} > {label}" if prefix else label
            if isinstance(value, str):
                out.append((section, value))
            elif isinstance(value, list):
                out.extend(_flatten_nav(value, prefix=section))
    return out


def _top_level_nav_labels(nav: list) -> set[str]:
    labels: set[str] = set()
    for entry in nav:
        if isinstance(entry, dict):
            labels.update(entry.keys())
    return labels


# ---------------------------------------------------------------------------
# Structural checks (no mkdocs build required)
# ---------------------------------------------------------------------------


def test_mkdocs_yml_loads() -> None:
    """`mkdocs.yml` is valid YAML."""
    cfg = _load_mkdocs_yml()
    assert cfg.get("site_name") == "alloy-cli"
    assert "nav" in cfg


def test_top_level_nav_contains_every_required_section() -> None:
    cfg = _load_mkdocs_yml()
    labels = _top_level_nav_labels(cfg["nav"])
    missing = [s for s in _REQUIRED_TOP_LEVEL_SECTIONS if s not in labels]
    assert not missing, (
        f"Top-level nav missing required sections: {missing}\n"
        f"Found: {sorted(labels)}"
    )


def test_every_docs_md_is_reachable() -> None:
    """Every `docs/**/*.md` file is reachable via the nav, the
    `not_in_nav:` exemption block, or the `mkdocs-redirects` map."""
    cfg = _load_mkdocs_yml()
    nav_pages = {doc for _, doc in _flatten_nav(cfg["nav"])}
    redirect_targets = _redirect_targets(cfg)

    not_in_nav_exemptions = _parse_not_in_nav(cfg.get("not_in_nav") or "")

    unreachable: list[str] = []
    for md in sorted(DOCS_DIR.rglob("*.md")):
        rel = md.relative_to(DOCS_DIR).as_posix()
        if rel in nav_pages:
            continue
        if rel in redirect_targets:
            continue
        if f"/{rel}" in not_in_nav_exemptions or rel in not_in_nav_exemptions:
            continue
        unreachable.append(rel)

    assert not unreachable, (
        "These docs/*.md files are not reachable from the nav, "
        "not exempted via `not_in_nav:`, and not a redirect target:\n  "
        + "\n  ".join(unreachable)
    )


def test_every_redirect_target_exists() -> None:
    """Every `mkdocs-redirects` entry points at a real file under docs/."""
    cfg = _load_mkdocs_yml()
    redirect_targets = _redirect_targets(cfg)
    missing: list[str] = []
    for target in sorted(redirect_targets):
        if not (DOCS_DIR / target).exists():
            missing.append(target)
    assert not missing, (
        "These redirect targets do not exist under docs/:\n  "
        + "\n  ".join(missing)
    )


def test_redirects_register_user_friendly_aliases() -> None:
    """The redirect map MUST register at least the lowercase-slug
    aliases listed in the spec (`/quickstart/`, `/recovery/`,
    `/cookbook/`, `/cheatsheet/`)."""
    cfg = _load_mkdocs_yml()
    sources = _redirect_sources(cfg)
    expected = ("quickstart.md", "recovery.md", "cookbook.md", "cheatsheet.md")
    missing = [a for a in expected if a not in sources]
    assert not missing, f"redirect_maps is missing user-friendly aliases: {missing}"


def test_landing_page_links_to_quickstart() -> None:
    """`docs/index.md` links to the Quickstart and includes the
    install one-liner (per spec scenario `the landing page links
    to the quickstart`)."""
    text = (DOCS_DIR / "index.md").read_text(encoding="utf-8")
    assert "QUICKSTART.md" in text
    assert "pip install alloy-cli" in text
    # The 4-tile feature grid + a TUI screenshot are also part of
    # the spec.
    assert "images/" in text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redirect_targets(cfg: dict) -> set[str]:
    """Collect target paths from the mkdocs-redirects plugin block."""
    plugins = cfg.get("plugins", []) or []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        if "redirects" in plugin:
            redirect_maps = (plugin["redirects"] or {}).get("redirect_maps", {})
            return set(redirect_maps.values())
    return set()


def _redirect_sources(cfg: dict) -> set[str]:
    """Collect source aliases from the mkdocs-redirects plugin block."""
    plugins = cfg.get("plugins", []) or []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        if "redirects" in plugin:
            redirect_maps = (plugin["redirects"] or {}).get("redirect_maps", {})
            return set(redirect_maps.keys())
    return set()


def _parse_not_in_nav(value: str) -> set[str]:
    """Parse the YAML literal-block `not_in_nav:` into a set of
    forward-slash-prefixed paths (mkdocs's expected shape)."""
    return {line.strip() for line in value.splitlines() if line.strip()}
