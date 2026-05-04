## Why

The repo ships ~5,400 lines of high-quality Markdown docs (QUICKSTART,
ARCHITECTURE, ERROR_COOKBOOK, three TOOLCHAIN_* references, RECOVERY,
VISION, ROADMAP, AI_INTEGRATION, …) but they live as a flat directory
of `*.md` files on GitHub.  A new contributor lands on the README, has
no entry-point map, no search, no dark mode, no auto-generated CLI
reference, and no way to deep-link a colleague to a specific section.
With four shipped capabilities (registry / installer / onboarding /
recovery) plus the typed orchestrator + MCP surface, the product is
mature enough to deserve a real documentation site.

Goal: build a **professional GitHub Pages docs site** powered by
**MkDocs Material** that surfaces every existing doc through a real
information architecture, auto-generates the CLI + API reference
from the source of truth (Click + docstrings), and stays green via
strict-mode CI.

## What Changes

- **New `docs/index.md`** landing page with hero, value-prop, install
  one-liner, "Why alloy-cli?" pull from VISION, 3-tile feature grid,
  CTA cards.  This is the page `https://alloy-embedded.github.io/
  alloy-cli/` opens to.
- **New `mkdocs.yml`** at repo root: Material theme, instant
  navigation, search-as-you-type, dark/light toggle, Mermaid
  diagrams, code-copy buttons, full IA tree (Home / Getting Started
  / User Guide / Reference / Concepts / Examples / Architecture /
  Contributing / API Reference / Changelog).
- **CLI reference auto-generated** via `mkdocs-click` against
  `alloy_cli.main:cli` — every `alloy <verb>` lands in the site
  without doc edits.
- **API reference auto-generated** via `mkdocstrings[python]` for
  `alloy_cli.core.{toolchain_orchestrator,probe_orchestrator,
  toolchain_registry,tool_sources,errors}`, `alloy_cli.mcp`, and
  `alloy_cli.tui` modules.
- **URL-stability via `mkdocs-redirects`** — every existing
  `docs/<X>.md` URL keeps resolving after the IA reorg (so
  external links / past commits / search-engine hits keep working).
- **New concept docs** for the parts of the system that aren't yet
  written up: device IR, the two orchestrator pattern, lockfile-aware
  execution, two-phase mutations.
- **Custom theming** via `docs/stylesheets/extra.css` (alloy-blue
  brand colour pulled from the TUI snapshots) + a logo / favicon.
- **GitHub Pages deployment** via a new `.github/workflows/docs.yml`
  workflow that builds on push to `main` and every `v*` tag, deploys
  via `mkdocs gh-deploy --force` to the `gh-pages` branch.
- **`pip install -e .[docs]`** — new optional-deps group lists every
  build-time + plugin dep.
- **Doc-quality regression tests** (`tests/test_docs_site_*.py`) so
  `mkdocs build --strict` runs in CI; broken nav / unresolved links
  fail the build.
- The four existing `docs/*` regression tests
  (`test_quickstart_and_cookbook.py`, `test_toolchain_installer_doc.
  py`, `test_toolchain_onboarding_doc.py`, `test_recovery_doc.py`)
  keep passing — content invariants survive the reorg.

## Capabilities

### New Capabilities

- `docs-site`: the MkDocs Material site config, the landing page, the
  navigation tree, the auto-generated CLI + API reference, the
  GitHub Pages CI workflow, and the doc-build regression tests.

### Modified Capabilities

- `developer-experience`: adds the `[docs]` extra to the install
  surface (`pip install -e .[docs]`) and adds the public docs site
  as a discoverable contributor surface.  No behavioural change to
  the existing developer-experience requirements.

## Impact

- **New deps (`[docs]` extra only)**: `mkdocs>=1.6`,
  `mkdocs-material>=9.5`, `mkdocstrings[python]>=0.26`,
  `mkdocs-click>=0.8`, `mkdocs-redirects>=1.2`,
  `mkdocs-include-markdown-plugin>=6`, `pymdown-extensions>=10`.
  No change to runtime install footprint — the extra is opt-in.
- **New CI surface**: `.github/workflows/docs.yml` uses Trusted
  Publishing (no PAT) to deploy to `gh-pages`.  Decoupled from
  `release.yml` so docs can ship independently.
- **No runtime impact**: zero changes to `src/alloy_cli/` source
  (apart from possibly improving a few docstrings the API reference
  surfaces).  No public API contracts move.
- **Existing docs preserved**: every `docs/*.md` file stays where
  it is.  `mkdocs.yml` references them by path; the IA emerges
  from the nav tree, not from filesystem layout.
- **Test surface grows by ~10 tests** (build-strict, link-resolve,
  IA-completeness).  Total suite stays green.
