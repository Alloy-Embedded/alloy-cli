## 1. Skeleton — `mkdocs.yml` + `docs/index.md` + `[docs]` extra

- [x] 1.1 Add the `[docs]` optional-dependencies group to `pyproject.toml` listing `mkdocs>=1.6`, `mkdocs-material>=9.5`, `mkdocstrings[python]>=0.26`, `mkdocs-click>=0.8`, `mkdocs-redirects>=1.2`, `mkdocs-include-markdown-plugin>=6`, `pymdown-extensions>=10`.
- [x] 1.2 Author the root `mkdocs.yml` with `site_name`, `site_description`, `site_url`, `repo_url`, `repo_name`, `edit_uri` pointing at the canonical alloy-cli GitHub URLs.  Configure the Material theme with light + dark palettes (`primary: indigo`, `accent: deep orange`), instant navigation, search-as-you-type, code-copy buttons, and the dark-mode toggle (default light, `localStorage` persistence).
- [x] 1.3 Author the new `docs/index.md` landing page: hero with project tagline + `pip install alloy-cli` one-liner, "Why alloy-cli?" pull from VISION.md (3-4 sentences), 3-tile feature grid (Scaffold / Build / AI-native), CTA card linking to the Quickstart, embedded TUI snapshot from `docs/images/02-dashboard.svg` (or `01-welcome.svg`).
- [x] 1.4 Run `mkdocs serve` locally; confirm the landing page renders, the dark-mode toggle works, and the install one-liner copies via the code-copy button.

## 2. Full nav tree — every existing doc reachable

- [x] 2.1 Wire the nav tree in `mkdocs.yml` matching the IA from the proposal: `Home` → `index.md`; `Getting Started` (Quickstart, Installation, Your first project); `User Guide` (Scaffolding, Configuration, Build & Flash, Toolchain management with three sub-pages, Recovery, TUI dashboard, AI integration); `Reference` (CLI commands, alloy.toml schema, Family manifest schema, Source pin file schema, MCP tools, Error cookbook, Cheatsheet); `Concepts` (Device IR, Toolchain orchestrator, Probe orchestrator, Lockfile-aware execution, Two-phase mutations); `Examples` (linked to docs/EXAMPLES); `Architecture & Design`; `Contributing`; `API Reference`; `Changelog`.
- [x] 2.2 Author the new `Concepts` doc stubs (5 small pages, ~50-100 lines each): `concepts/device-ir.md`, `concepts/toolchain-orchestrator.md`, `concepts/probe-orchestrator.md`, `concepts/lockfile-aware-execution.md`, `concepts/two-phase-mutations.md`.  Each pulls the existing material from the README + RECOVERY + TOOLCHAIN_ONBOARDING into a focused conceptual narrative.
- [x] 2.3 Author the new `Getting Started/Installation` page splitting the install steps out of QUICKSTART into a dedicated page (covers system requirements, `pip install alloy-cli`, optional extras, verifying with `alloy --version`).
- [x] 2.4 Author the new `Getting Started/Your first project` page: a deep walkthrough that goes beyond the 5-min QUICKSTART (adds peripherals, explains the IR validation, walks through the doctor + cookbook).
- [x] 2.5 Author the new `User Guide` index pages for each section that needs an introduction (Toolchain management, Recovery).  Single-paragraph pages that link to the existing `TOOLCHAIN_*.md` / `RECOVERY.md` files.
- [x] 2.6 Run `mkdocs build --strict` locally; confirm zero warnings; confirm every nav entry resolves to a real file.

## 3. Auto-generated CLI + API references

- [x] 3.1 Configure `mkdocs-click` plugin in `mkdocs.yml` and create `docs/reference/cli.md` with a `:::click:` directive against `alloy_cli.main:cli` (renders every `alloy <verb>` automatically).
- [x] 3.2 Configure `mkdocstrings[python]` plugin in `mkdocs.yml` with the Google docstring style, `show_source: true`, `heading_level: 2`, `filters: ["!^_"]` (private filter).
- [x] 3.3 Create `docs/api/` with one page per allowlisted module: `api/toolchain-orchestrator.md`, `api/probe-orchestrator.md`, `api/toolchain-registry.md`, `api/tool-sources.md`, `api/errors.md`, `api/mcp.md`, `api/tui-screens.md`.  Each page uses the `::: alloy_cli.<module>` directive.
- [x] 3.4 Add the `API Reference` section to the nav with one entry per module page.
- [x] 3.5 Re-run `mkdocs build --strict`; confirm every `mkdocstrings` reference resolves; confirm the `mkdocs-click` page renders all 18 commands; confirm filtering hides private symbols.

## 4. URL stability — `mkdocs-redirects`

- [x] 4.1 Configure `mkdocs-redirects` plugin in `mkdocs.yml` and author the `redirect_maps` block mapping every existing top-level `docs/*.md` to its new IA path (QUICKSTART → getting-started/quickstart, ARCHITECTURE → architecture/overview, TOOLCHAIN_REGISTRY → user-guide/toolchain/registry, TOOLCHAIN_INSTALLER → user-guide/toolchain/installer, TOOLCHAIN_ONBOARDING → user-guide/toolchain/onboarding, RECOVERY → user-guide/recovery, ERROR_COOKBOOK → reference/errors, AI_INTEGRATION → user-guide/ai-integration, CHEATSHEET → reference/cheatsheet, ARCHITECTURE / TUI_DESIGN / DATA_SOURCES / PROJECT_FORMAT / COMPARISON → architecture/*, ROADMAP / RELEASING / CONTRIBUTING / VISION / REVIEW → contributing/* or about/*).
- [x] 4.2 Confirm every redirect target file exists OR has a corresponding nav entry under the new IA path.
- [x] 4.3 Run `mkdocs build --strict`; visit `/QUICKSTART/` in the served site and confirm it redirects to the new path.

## 5. Theming + branding

- [ ] 5.1 Create `docs/stylesheets/extra.css` with: brand-colour overrides (alloy-blue / amber accent matching the TUI snapshots), print-friendly overrides (no header/footer in print, ink-friendly syntax-highlight palette), hero-card styling for the landing page, a slightly larger code-block font for embedded TUI SVGs.
- [ ] 5.2 Reference `extra.css` in `mkdocs.yml`'s `extra_css:` block.
- [ ] 5.3 Generate or pick a logo + favicon: a simple wordmark "alloy" rendered in the brand colour, exported as 192x192 PNG (logo) + multi-size ICO (favicon).  Drop both at `docs/assets/logo.png` + `docs/assets/favicon.ico`.  Reference them in the Material theme's `logo:` and `favicon:` keys.
- [ ] 5.4 Enable Mermaid diagram support via `pymdownx.superfences` with the `mermaid` custom-fence config so architecture pages can include flow diagrams.
- [ ] 5.5 Author one Mermaid diagram in `concepts/toolchain-orchestrator.md` showing the five entry points → `install_family` fan-in.
- [ ] 5.6 Author one Mermaid diagram in `concepts/probe-orchestrator.md` showing the three CLI verbs + TUI + MCP → `probe_orchestrator` fan-in.
- [ ] 5.7 Run `mkdocs build --strict`; confirm both diagrams render in the rendered HTML.

## 6. CI deployment — `.github/workflows/docs.yml`

- [ ] 6.1 Author `.github/workflows/docs.yml` with: triggers (`push: branches: [main]`, `push: tags: ['v*']`, `workflow_dispatch`), single `deploy` job, concurrency group `docs-deploy` with `cancel-in-progress: true`.
- [ ] 6.2 In the deploy job: `actions/checkout@v4` with `fetch-depth: 0` (so `git revision date` plugins resolve correctly); `actions/setup-python@v5` pinning Python 3.13; `pip install -e .[docs]`; `mkdocs gh-deploy --force --strict`.
- [ ] 6.3 Set the workflow's `permissions:` to `contents: write` so `mkdocs gh-deploy` can push to the `gh-pages` branch.  Use the default `GITHUB_TOKEN` (no PAT needed).
- [ ] 6.4 Add a placeholder `docs/CNAME` file (commented out / .example suffix) for the user to enable a custom domain when registered.  Document it in the workflow's README block.
- [ ] 6.5 First-deploy dry-run: trigger the workflow manually via `workflow_dispatch`; verify the `gh-pages` branch is created + populated; verify GitHub Pages settings auto-detect it; verify `https://alloy-embedded.github.io/alloy-cli/` serves the rendered site.

## 7. Doc-quality regression tests

- [ ] 7.1 Create `tests/test_docs_site_build.py` invoking `mkdocs build --strict` against the repo's `mkdocs.yml` in a tmpdir; assert exit code 0, zero warnings on stderr, `site/index.html` exists.
- [ ] 7.2 Create `tests/test_docs_site_links.py` walking `site/**/*.html`, parsing every `<a href="...">`, and resolving each internal target.  Skip external `http(s)://` and `mailto:` URLs.  Assert every internal anchor resolves to a real file (or in-page anchor).
- [ ] 7.3 Create `tests/test_docs_site_ia.py` parsing `mkdocs.yml` (via PyYAML); assert the top-level nav contains every section listed in the IA spec; walk every `docs/*.md` file and assert it's reachable via either the nav OR the redirects map.
- [ ] 7.4 Pin the new tests with `pytest.mark.docs` so contributors who haven't installed `[docs]` extras get a skip rather than an import-error.  Configure the marker in `conftest.py` or `pyproject.toml` `[tool.pytest.ini_options]`.

## 8. README link + CHANGELOG + validation + archive

- [ ] 8.1 Update the top of `README.md` (above the screenshot grid) with a banner-style link to the deployed docs site (`https://alloy-embedded.github.io/alloy-cli/`).  Single line, above-the-fold.
- [ ] 8.2 Run `openspec validate add-docs-site --strict`; resolve any reported issue.
- [ ] 8.3 Run targeted tests: `pytest tests/test_docs_site_build.py tests/test_docs_site_links.py tests/test_docs_site_ia.py tests/test_quickstart_and_cookbook.py tests/test_toolchain_installer_doc.py tests/test_toolchain_onboarding_doc.py tests/test_recovery_doc.py`.  Confirm green.
- [ ] 8.4 Run `pytest -q --deselect tests/test_mcp_server.py::test_alloy_mcp_serve_stdio_round_trips_via_subprocess` (and the four pre-Wave-3 environmental deselects).  Confirm green.
- [ ] 8.5 Run `ruff check src tests scripts` and `pyright src/alloy_cli`.  Resolve any new finding.
- [ ] 8.6 Update `CHANGELOG.md` under `[Unreleased]` with a "Documentation site" entry naming the new `[docs]` extra, the IA tree, the auto-generated CLI + API reference, the GitHub Pages deployment, and the URL-stability redirects.
- [ ] 8.7 Open the PR titled `Implement add-docs-site` referencing this OpenSpec change in the description.  When merged, archive via `openspec archive add-docs-site`.
