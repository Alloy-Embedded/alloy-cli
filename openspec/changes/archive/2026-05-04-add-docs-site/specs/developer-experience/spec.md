## ADDED Requirements

### Requirement: alloy-cli SHALL expose a `[docs]` install extra

The `pyproject.toml` SHALL declare an optional-dependencies group
named `docs` that lists every dependency required to build the
documentation site (mkdocs, mkdocs-material, mkdocstrings[python],
mkdocs-click, mkdocs-redirects, mkdocs-include-markdown-plugin,
pymdown-extensions).  Contributors SHALL be able to install the
build prerequisites with `pip install -e .[docs]`.

#### Scenario: `pip install -e .[docs]` resolves every doc-build dep

- **WHEN** a contributor runs `pip install -e .[docs]` in a clean
  virtual environment
- **THEN** every dependency required by `mkdocs build --strict`
  SHALL be installed
- **AND** running `mkdocs --version` SHALL print a non-empty
  version string
- **AND** running `mkdocs build --strict` against the repo's
  `mkdocs.yml` SHALL succeed

#### Scenario: the runtime install does NOT pull doc-build deps

- **WHEN** a user runs `pip install alloy-cli` without extras
- **THEN** `mkdocs` SHALL NOT be installed
- **AND** `pip show alloy-cli | grep Requires` SHALL NOT list any
  doc-build dependency
- **AND** importing `alloy_cli` SHALL succeed without the docs
  extras

### Requirement: alloy-cli SHALL surface the public docs site as a contributor entry point

The `README.md` SHALL link to the deployed docs site
(`https://alloy-embedded.github.io/alloy-cli/`) as the canonical
"learn more" entry point.  Contributors landing on the GitHub
project page SHALL be able to reach the rendered site within one
click.

#### Scenario: the README links to the deployed docs site

- **WHEN** the test suite parses `README.md`
- **THEN** the file SHALL contain a link to the GitHub Pages URL
  for the project (`alloy-embedded.github.io/alloy-cli` or the
  configured custom domain)
- **AND** the link's anchor text SHALL be discoverable in the
  first 30 lines (top of the README, above the fold)
