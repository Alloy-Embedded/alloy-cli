# docs-site Specification

## Purpose
TBD - created by archiving change add-docs-site. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL ship a buildable documentation site

The repo SHALL include `mkdocs.yml` at the root and a working
`docs/index.md` such that `mkdocs build --strict` succeeds without
warnings.  The build SHALL produce a `site/` tree of static HTML
that any HTTP server can serve.

#### Scenario: mkdocs build --strict succeeds

- **WHEN** a contributor runs `mkdocs build --strict` after
  installing `pip install -e .[docs]`
- **THEN** the command SHALL exit 0
- **AND** the build SHALL emit zero warnings
- **AND** `site/index.html` SHALL exist and contain the project
  tagline

#### Scenario: mkdocs serve renders the site locally

- **WHEN** a contributor runs `mkdocs serve` after the install
  above
- **THEN** the command SHALL start an HTTP server on port 8000
- **AND** `http://127.0.0.1:8000/` SHALL render the landing page
- **AND** the navigation tree SHALL be discoverable from every page

### Requirement: the navigation tree SHALL cover every existing top-level doc

Every `docs/*.md` file shipped before this proposal SHALL be
reachable via the rendered site, either through a direct nav
entry OR through a `mkdocs-redirects` mapping registered in
`mkdocs.yml`.  The IA SHALL match the structure documented in
the proposal (Home / Getting Started / User Guide / Reference /
Concepts / Examples / Architecture & Design / Contributing /
API Reference / Changelog).

#### Scenario: every existing doc resolves through the site

- **WHEN** the test suite walks every file under `docs/*.md`
- **THEN** for each file, either:
  - the file SHALL appear in `mkdocs.yml`'s `nav:` tree, OR
  - the file's filename (without `.md`) SHALL appear as a key in
    the `mkdocs-redirects` `redirect_maps` block

#### Scenario: the IA top-level matches the spec

- **WHEN** the test suite parses `mkdocs.yml`'s `nav:` tree
- **THEN** the top-level entries SHALL include `Home`,
  `Getting Started`, `User Guide`, `Reference`, `Concepts`,
  `Examples`, `Architecture & Design`, `Contributing`,
  `API Reference`, `Changelog`

### Requirement: the CLI reference SHALL be auto-generated from Click

The site's CLI reference page SHALL render every `alloy <verb>`
through `mkdocs-click` against `alloy_cli.main:cli`.  Adding a new
Click command in `commands/` SHALL surface the new verb on the next
build without doc edits.

#### Scenario: every alloy verb surfaces in the CLI reference

- **WHEN** the rendered site is built
- **THEN** `site/reference/cli/` (or equivalent) SHALL contain a
  section for every command registered on `cli` (including `new`,
  `build`, `flash`, `debug`, `boards`, `devices`, `add`, `ui`,
  `mcp`, `chat`, `doctor`, `toolchain`, `update`, `export`,
  `setup`, `reset`, `erase`, `monitor`)

### Requirement: the API reference SHALL be auto-generated from docstrings

The site's API reference SHALL render every public symbol in a
configured allowlist of modules through `mkdocstrings[python]`.
The allowlist SHALL include
`alloy_cli.core.toolchain_orchestrator`,
`alloy_cli.core.probe_orchestrator`,
`alloy_cli.core.toolchain_registry`,
`alloy_cli.core.tool_sources`, `alloy_cli.core.errors`,
`alloy_cli.mcp`, and the `alloy_cli.tui.screens.*` modules.
Private symbols (names starting with `_`) SHALL be filtered out.

#### Scenario: orchestrator symbols appear on the API page

- **WHEN** the rendered site is built
- **THEN** the page for
  `alloy_cli.core.toolchain_orchestrator` SHALL include the
  `install_family` function, every `InstallEvent` subclass
  (`ToolStarted`, `ToolDownloaded`, `ToolInstalled`, `ToolFailed`,
  `ToolSkippedVendor`, `ToolSkippedHostUnsupported`),
  `InstallOutcome`, `InstallReport`, and `InstallPlanItem`

#### Scenario: probe-orchestrator symbols appear on the API page

- **WHEN** the rendered site is built
- **THEN** the page for `alloy_cli.core.probe_orchestrator` SHALL
  include `select_probe`, `reset_target`, `plan_erase`,
  `execute_erase`, `open_monitor`, `real_probe_for`,
  `ProbeIdentity`, every `MonitorEvent` subclass, and
  `MonitorSessionTable`

### Requirement: every existing docs URL SHALL keep resolving

The site SHALL preserve every URL of the form `/<DOC>/` (e.g.
`/QUICKSTART/`) corresponding to a previously-shipped
`docs/<DOC>.md`.  Implementation strategy: source files DO NOT
move under the IA reorg; the navigation tree groups them
editorially.  This keeps every flat URL canonical and resolves
external links / search-engine hits trivially.  The
`mkdocs-redirects` plugin SHALL also register convenience
aliases (e.g. `/quickstart/` → `/QUICKSTART/`) so user-friendly
slugs work too.

#### Scenario: legacy flat URLs render directly

- **WHEN** a browser requests `/QUICKSTART/` on the deployed site
- **THEN** the server SHALL render the page directly (no
  redirect needed — source file lives at `docs/QUICKSTART.md`)
- **AND** the page content SHALL match the source file

#### Scenario: user-friendly aliases redirect to the canonical URL

- **WHEN** a browser requests `/quickstart/` (lowercase) on the
  deployed site
- **THEN** the server SHALL respond with a redirect (or a meta
  refresh) to `/QUICKSTART/`

#### Scenario: every redirect target exists

- **WHEN** the test suite walks the `mkdocs-redirects`
  `redirect_maps` block
- **THEN** for each `<source>: <target>` entry, the target
  SHALL exist as a file under `docs/` (so the redirect points at
  a real, build-able page)

### Requirement: the site SHALL be deployed via GitHub Pages on every main push and tag

A new `.github/workflows/docs.yml` workflow SHALL build the site
with `--strict` and deploy it to the `gh-pages` branch via
`mkdocs gh-deploy --force`.  The workflow SHALL trigger on every
push to `main`, every push of a `v*` tag, and on manual dispatch.
The workflow SHALL use a concurrency group so a fast `main` push
does not race with a tag-build deploy.

#### Scenario: pushing to main triggers a docs deploy

- **WHEN** a commit lands on `main`
- **THEN** `.github/workflows/docs.yml` SHALL run
- **AND** on success, the `gh-pages` branch SHALL contain the
  freshly-built `site/` content

#### Scenario: pushing a v* tag triggers a docs deploy

- **WHEN** a `v*` tag is pushed
- **THEN** `.github/workflows/docs.yml` SHALL run
- **AND** the existing `release.yml` workflow SHALL ALSO run
  independently (PyPI publish + docs deploy are decoupled)

#### Scenario: a docs-only commit does not trigger PyPI publish

- **WHEN** a commit lands on `main` that touches only `docs/**`,
  `mkdocs.yml`, or `.github/workflows/docs.yml`
- **THEN** `release.yml` SHALL NOT run
- **AND** PyPI SHALL NOT receive a publish

### Requirement: the strict build SHALL gate every CI deploy

The `docs.yml` workflow SHALL invoke `mkdocs build --strict` (or
`mkdocs gh-deploy --strict`).  Any unresolved nav entry, broken
internal link, malformed YAML, missing plugin, or broken
`mkdocstrings`/`mkdocs-click` reference SHALL fail the workflow
and PREVENT the deploy.

#### Scenario: a broken link fails the docs workflow

- **WHEN** a commit introduces a Markdown link to a non-existent
  page (e.g. `[See here](nope.md)`)
- **THEN** `mkdocs build --strict` SHALL exit non-zero
- **AND** the `docs.yml` workflow SHALL fail
- **AND** the previous `gh-pages` content SHALL stay deployed
  (the failed deploy SHALL NOT overwrite the live site)

### Requirement: doc-quality regression tests SHALL guard the structural invariants

The repo SHALL include three new test files exercising the site's
structural invariants beyond what `--strict` catches.

#### Scenario: tests/test_docs_site_build.py asserts the build is green

- **WHEN** the test suite runs
  `tests/test_docs_site_build.py`
- **THEN** the test SHALL invoke `mkdocs build --strict` against
  the repo's `mkdocs.yml`
- **AND** the test SHALL PASS only when the build emits zero
  warnings AND zero errors

#### Scenario: tests/test_docs_site_links.py asserts every internal link resolves

- **WHEN** the test suite runs
  `tests/test_docs_site_links.py`
- **THEN** the test SHALL walk the rendered `site/**/*.html` tree
  and resolve every `<a href="...">` whose target is internal
- **AND** the test SHALL PASS only when every internal anchor and
  page reference resolves to a real file

#### Scenario: tests/test_docs_site_ia.py asserts the IA tree is complete

- **WHEN** the test suite runs `tests/test_docs_site_ia.py`
- **THEN** the test SHALL parse `mkdocs.yml` and assert:
  - the top-level nav contains every section listed in the IA
    spec (Home / Getting Started / User Guide / Reference /
    Concepts / Examples / Architecture & Design / Contributing /
    API Reference / Changelog), AND
  - every existing `docs/<X>.md` file is reachable via either
    the nav tree or the `mkdocs-redirects` map, AND
  - every redirect target is itself a real file under `docs/`

### Requirement: the site SHALL render in dark mode

The Material theme SHALL configure both light + dark palettes with
a toggle.  The user's preference SHALL persist via `localStorage`
(default Material behaviour).

#### Scenario: the dark-mode toggle is present and functional

- **WHEN** a user loads any rendered page
- **THEN** the page SHALL include a theme-toggle control
- **AND** clicking the toggle SHALL flip between the configured
  light + dark palettes
- **AND** reloading the page SHALL preserve the chosen mode

### Requirement: the landing page SHALL guide a new user to first ELF in five minutes

`docs/index.md` SHALL render a hero section, the install
one-liner, a "Why alloy-cli?" pull from VISION.md, a 3-tile feature
grid (Scaffold / Build / AI-native), and a CTA card linking to the
Quickstart.  The landing page SHALL embed at least one TUI
snapshot from `docs/images/`.

#### Scenario: the landing page links to the quickstart

- **WHEN** the test suite parses `docs/index.md`
- **THEN** the file SHALL contain a link with text matching
  `Quickstart` (case-insensitive) pointing at the Quickstart page
  (either `getting-started/quickstart/` or `QUICKSTART.md`)
- **AND** the file SHALL contain the install one-liner
  `pip install alloy-cli`

#### Scenario: the landing page embeds a TUI screenshot

- **WHEN** the rendered `site/index.html` is parsed
- **THEN** the page SHALL include at least one `<img>` tag
  whose `src` resolves to a file under `docs/images/`

