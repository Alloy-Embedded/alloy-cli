## Context

The repo currently exposes documentation through:

- **GitHub-rendered Markdown** at `docs/*.md` (no nav, no search,
  no IA, no auto-doc).
- **`README.md`** which links into the docs by relative path.
- **`scripts/generate_cheatsheet.py`** which regenerates
  `docs/CHEATSHEET.md` from the Click tree.
- **`scripts/generate_docs_images.py`** which renders TUI snapshots
  to `docs/images/*.svg`.

Four shipped capabilities (registry / installer / onboarding /
recovery) plus the typed orchestrator + MCP surface mean the
content set is mature.  What's missing is the rendering layer —
a real site with nav, search, dark mode, deep linkability, and
auto-generated CLI + API references that stay in sync with the
source.

The `release.yml` workflow already publishes to PyPI on every `v*`
tag.  The docs deployment must be **decoupled** so a docs-only
change doesn't trigger a publish, and a release tag publishes both.

GitHub Pages is the obvious target: free, zero infra, supports
custom domains, has first-class support in MkDocs Material.

## Goals / Non-Goals

**Goals:**

- Single command (`mkdocs serve`) to preview the full site locally.
- Single CI job (`docs.yml`) that builds + deploys on `main` push +
  `v*` tag + manual dispatch, using Trusted Publishing (no PAT).
- Information architecture maps every existing `docs/*.md` to a
  navigable nav entry, AND surfaces auto-generated CLI + API
  references that stay current.
- Strict-mode CI: any unresolved nav entry, broken link, or missing
  page fails the build.
- URL stability: every existing `docs/<X>.md` URL keeps resolving
  via `mkdocs-redirects` after the IA reorg.
- Search-as-you-type, dark mode, code-copy buttons, Mermaid diagram
  rendering — all out-of-the-box from Material.
- Doc-quality regression tests (`test_docs_site_*.py`) guard the
  invariants beyond what the strict build catches.

**Non-Goals:**

- Versioned docs (multi-version switcher via `mike`).  Single
  "latest" version that tracks `main` for now; revisit at v1.0.
- Custom domain.  The site lives at `https://alloy-embedded.github.
  io/alloy-cli/` until the user registers one.
- i18n / translations.
- Algolia DocSearch.  The Material built-in search is sufficient.
- Self-hosted documentation server.  GH Pages is free + sufficient.
- Per-release frozen API snapshots.  Material supports this, but
  adds CI complexity; revisit at v1.0.
- Editing existing `docs/*.md` content.  The IA reorg happens in
  `mkdocs.yml` nav, not by moving files.  Existing regression tests
  must continue to pass unchanged.

## Decisions

### D1: MkDocs Material as the static-site generator

**Decision:** Use **MkDocs Material**.

**Why:** De facto standard for Python CLI + library docs (FastAPI,
Pydantic, Typer, Textual, HTTPX, Rich all use it).  First-class
GitHub Pages integration.  Plugin ecosystem covers everything we
need (Click auto-doc, Python API auto-doc, redirects).  Active
maintenance + frequent releases.

**Alternatives considered:**

- **Sphinx + Furo / RTD theme.** Rejected: heavier, RST default
  (we have Markdown), slower iteration on layout, less polished
  out-of-the-box.  Better suited for science/research projects.
- **Docusaurus.** Rejected: Node toolchain alongside the Python
  one, MDX learning curve, overkill for a library doc site.
- **Hugo / Jekyll.** Rejected: no Python integration story; would
  have to roll our own CLI / API auto-doc.
- **VitePress.** Rejected: same Node-toolchain concern + smaller
  Python community.

### D2: Auto-generated CLI reference via `mkdocs-click`

**Decision:** Render the CLI reference page from
`alloy_cli.main:cli` using `mkdocs-click`.

**Why:** Click's `--help` output is the source of truth.  Any new
verb or flag added to `commands/` lands in the docs site
automatically — no second source to keep in sync.  Matches what
`docs/CHEATSHEET.md` does today (`scripts/generate_cheatsheet.py`),
but for the long-form per-verb docs.

**Alternatives considered:**

- **Hand-write the CLI reference.** Rejected: drift guaranteed;
  the cheatsheet experience already showed how easy it is to forget
  to regen.
- **`click-extra` + `argparse-manpage`.** Rejected: targets
  manpages, not the rendered HTML site flow we want.

The cheatsheet stays around as the "one-page printable reference";
the `mkdocs-click` page is the long-form per-verb explanation.

### D3: Auto-generated API reference via `mkdocstrings[python]`

**Decision:** Render every public module under `alloy_cli.core.*`,
`alloy_cli.mcp`, and `alloy_cli.tui.screens.*` via `mkdocstrings`
with the Google docstring style.

**Why:** Same rationale as D2: docstrings are the source of truth.
Every `frozen+slots` dataclass + every public function on the
orchestrators / MCP registry / TUI screens already has a docstring
because Wave 1–4 wrote them deliberately.  Auto-doc surfaces them
without a second source.  Cross-references between docs and API
reference work automatically (`[install_family][...]` links to the
API page).

**Alternatives considered:**

- **`pdoc3`.** Rejected: less polished output, no Material
  integration.
- **Hand-write every API table.** Rejected: would double the
  maintenance burden of every new dataclass field.

The render config uses `show_source: true` (link to GitHub) +
`heading_level: 2` so the page reads as a normal narrative.

### D4: URL stability via `mkdocs-redirects`

**Decision:** Mount a `mkdocs-redirects` config that maps each
existing top-level `docs/<X>.md` to its new IA location.

**Why:** External links to `https://github.com/Alloy-Embedded/
alloy-cli/blob/main/docs/QUICKSTART.md` exist (PRs, issues, blog
posts, the README itself).  When the IA reorg moves `QUICKSTART`
under `Getting Started/Quickstart`, the GH-pages URL becomes
`/getting-started/quickstart/`.  The redirects plugin keeps
`/QUICKSTART/` working.

**Mapping (subset):**

```yaml
plugins:
  - redirects:
      redirect_maps:
        QUICKSTART.md:                 getting-started/quickstart.md
        ARCHITECTURE.md:               architecture/overview.md
        TOOLCHAIN_REGISTRY.md:         user-guide/toolchain/registry.md
        TOOLCHAIN_INSTALLER.md:        user-guide/toolchain/installer.md
        TOOLCHAIN_ONBOARDING.md:       user-guide/toolchain/onboarding.md
        RECOVERY.md:                   user-guide/recovery.md
        ERROR_COOKBOOK.md:             reference/errors.md
        AI_INTEGRATION.md:             user-guide/ai-integration.md
        # … one entry per existing doc.
```

**Alternatives considered:**

- **Move the source files, accept broken links.** Rejected: GitHub
  source links break, search-engine hits return 404.
- **Symlinks at build time.** Rejected: not portable to Windows,
  brittle.
- **Keep flat IA, no reorg.** Rejected: defeats the point of
  building a real site.

### D5: GitHub Pages deployment via `gh-pages` branch

**Decision:** Use `mkdocs gh-deploy --force` from a workflow that
runs on `main` push + `v*` tag + manual dispatch.

**Why:** Two deployment models exist:

1. **Pages from a branch (`gh-pages`)** — `mkdocs gh-deploy` writes
   the built HTML to a `gh-pages` branch; GitHub serves it.
2. **Pages from Actions** — newer model; requires
   `actions/deploy-pages@v4` + the Pages site enabled in repo
   settings.

We pick model 1 because it's simpler, requires zero repo-settings
changes the user has to click, and works on any GitHub plan.
Model 2 has cleaner provenance (Sigstore signing); we can migrate
later without breaking URLs.

**Workflow concurrency:**

```yaml
concurrency:
  group: docs-deploy
  cancel-in-progress: true
```

So a fast `main` push doesn't race with a slower tag-build deploy.

**Alternatives considered:**

- **`actions/deploy-pages@v4`.** Rejected for now (extra setup
  step); revisit when we want signed artefacts.
- **Netlify / Cloudflare Pages.** Rejected: lock-in to a third
  party, free-tier limits, no clear win over GH Pages.

### D6: Strict-mode build is the sole nav-correctness gate

**Decision:** Run `mkdocs build --strict` in CI; trust the strict
flag to catch unresolved nav entries, missing pages, broken
auto-doc references.

**Why:** `--strict` already turns warnings into errors for: missing
nav entries, broken links to non-existent pages, malformed YAML,
unknown plugins, broken `mkdocstrings` references.  Layered tests
(`test_docs_site_build.py`, `test_docs_site_links.py`) add the
*integration* checks the strict flag can't catch:

- Every existing `docs/*.md` is reachable from the nav (or via a
  redirect).
- Every internal link in the rendered HTML resolves (rendered HTML
  is post-redirect, post-include).
- The IA tree shape matches the spec (top-level sections present).

**Alternatives considered:**

- **Custom Sphinx-style "nitpicky" mode.** Rejected: MkDocs strict
  already covers the warnings we care about; reinventing is waste.
- **Skip the integration tests, rely on strict only.** Rejected:
  strict doesn't catch redirects that point at moved-then-deleted
  files, or links to anchors that don't exist on the target page.

### D7: Nav tree IA — file-locality over MkDocs auto-nav

**Decision:** Hand-author the nav tree in `mkdocs.yml`.

**Why:** MkDocs supports auto-nav (sort by filename / front-matter
weight), but our content has 21 docs with no obvious lexical order.
The IA in the proposal is editorial: "Getting Started → User Guide
→ Reference → Concepts → Examples → Architecture → Contributing
→ API Reference → Changelog".  That ordering is intentional and
must be explicit.

The nav lives in `mkdocs.yml`; the file paths it points at don't
move.  This decouples the render-order from filesystem layout —
exactly what we want.

**Alternatives considered:**

- **Auto-nav with `nav_generator` plugin.** Rejected: would force
  a filesystem reorg to get the right order, breaking external
  links.
- **Front-matter `nav_weight` on every file.** Rejected: 21 files
  to touch; goes against the "don't edit existing docs" goal.

### D8: Theme + branding

**Decision:** Material theme, colour palette
`primary: indigo` / `accent: deep orange`.  Logo + favicon
generated as a simple wordmark from the existing TUI snapshot
palette.  Light mode is default; dark mode toggle persists in
`localStorage`.

**Why:** Indigo + deep orange echoes the alloy-blue / amber accent
the TUI uses (visible in `docs/images/01-welcome.svg`).  Material's
palette system handles both modes for free.  A simple wordmark
ships now; a polished logo can replace it later without rebuilding
anything.

**Custom CSS** (`docs/stylesheets/extra.css`):

- Print-friendly overrides (no header/footer, ink-friendly
  syntax-highlight palette).
- Larger code blocks for the embedded TUI snapshots.
- Hero-card styling for the landing page.

**Alternatives considered:**

- **Default Material colours.** Rejected: reads as generic; the
  brand-recognition value of the TUI's palette is real.
- **Custom theme from scratch.** Rejected: ~100x the maintenance
  burden for a < 100k-monthly-visitor site.

### D9: Doc-quality regression tests (extending the existing pattern)

**Decision:** Add three new test files mirroring the Wave 3 + Wave 4
doc-regression pattern.

- `tests/test_docs_site_build.py` — `mkdocs build --strict` runs
  green; the build emits no warnings; every page in the nav exists.
- `tests/test_docs_site_links.py` — every internal link in the
  rendered `site/**/*.html` resolves (no broken `<a href="...">`).
- `tests/test_docs_site_ia.py` — the nav tree contains every top-
  level section the IA spec mandates; every existing `docs/*.md`
  is either in the nav OR redirect-mapped.

The four existing `test_*_doc.py` files (QUICKSTART + COOKBOOK +
TOOLCHAIN_INSTALLER + TOOLCHAIN_ONBOARDING + RECOVERY) keep
running unchanged; they assert *content* invariants, the new tests
assert *structural* invariants.

**Alternatives considered:**

- **One mega-test file.** Rejected: harder to navigate when
  something fails; the per-concern split aids debugging.
- **No tests, trust strict-build.** Rejected per D6.

## Risks / Trade-offs

- **[Risk] `mkdocs build --strict` breaks on every commit until the
  initial nav stabilises.** → **Mitigation:** Develop the nav
  incrementally (root → User Guide → Reference → Concepts), running
  `mkdocs serve` locally; only enable `--strict` in CI once the
  build is green locally.

- **[Risk] `mkdocstrings` discovers undocumented private surfaces
  and bloats the API reference.** → **Mitigation:** Configure
  `filters: ["!^_"]` so `_private` names stay off the page; only
  document the modules listed in D3 (no globbing).

- **[Risk] The `gh-pages` branch grows unboundedly** (every deploy
  pushes a new commit). → **Mitigation:** `mkdocs gh-deploy
  --force` rebases/squashes by default; the branch stays one-deep.
  Track size in `docs.yml`; set a yearly garbage-collect reminder.

- **[Risk] A docs-only commit triggers the existing `release.yml`
  workflow.** → **Mitigation:** `release.yml` only fires on `v*`
  tags + manual dispatch (verified).  `docs.yml` only deploys (no
  PyPI publish).  The two are decoupled.

- **[Risk] The `mkdocs-redirects` map drifts from the actual
  filesystem moves.** → **Mitigation:** A regression test
  (`test_docs_site_ia.py`) walks the map and asserts every target
  page exists; broken redirects fail the build.

- **[Risk] External browsers cache the old `docs/X.md` URL
  structure.** → **Not really a risk** — those URLs continue to
  work via `mkdocs-redirects` AND through GitHub's source view
  (the source files don't move).

- **[Trade-off] No version switcher means the site always shows
  the latest `main` content, even for users on older releases.**
  → **Acceptable for now**: pre-1.0, breaking changes are flagged
  in the CHANGELOG.  Revisit at v1.0 with `mike`.

## Migration Plan

1. **Group 1**: ship the skeleton — `mkdocs.yml` + `docs/index.md`
   + `pyproject.toml` `[docs]` extra + minimal nav covering only
   the Getting Started tree.  `mkdocs serve` works locally.

2. **Group 2**: full nav — User Guide / Reference / Concepts /
   Examples / Architecture / Contributing branches all reference
   real existing files.  Strict build green locally.

3. **Group 3**: auto-doc — `mkdocs-click` for the CLI reference,
   `mkdocstrings` for the API reference.  Strict build still green.

4. **Group 4**: redirects — `mkdocs-redirects` map for every
   existing top-level `docs/*.md`.  All URL-stability tests green.

5. **Group 5**: theming + branding — custom CSS, palette, logo,
   favicon.  Mermaid plugin enabled for architecture pages.

6. **Group 6**: CI deployment — `.github/workflows/docs.yml`
   builds + deploys.  First successful publish to `gh-pages`.

7. **Group 7**: doc-quality regression tests — three new
   `test_docs_site_*.py` files lock the structural invariants.

8. **Group 8**: validation + CHANGELOG entry + archive.

Rollback strategy at any step: revert the offending commit; the
previous `gh-pages` branch state stays serving until the next
deploy.

## Open Questions

- **Custom domain?** Out of scope per the proposal.  When the user
  registers `docs.alloy-embedded.dev` (or similar), enable the
  `docs/CNAME` placeholder + flip the GH Pages settings.  No code
  change needed.
- **Should we ship terminal recordings (asciinema) for the
  landing page?** Defer to a follow-up — the static SVG renders we
  already have at `docs/images/*.svg` are sufficient for v0.5.0.
- **`mike` versioning at v1.0?** Yes — the v1.0 proposal will own
  it.  Until then, `latest` tracks `main`.
