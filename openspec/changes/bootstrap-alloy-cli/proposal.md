# Bootstrap alloy-cli

## Why

This is repo-zero for `alloy-cli` — the terminal-native developer
surface for the Alloy embedded platform.  Before any user-visible
feature, we need:

- A pip-installable Python package with `alloy` as the entry point.
- A versioning + release story tied to the rest of the Alloy
  ecosystem.
- A CI scaffold (lint / type / unit tests) running on every PR.
- A code style + license decision committed.
- A migration plan for `alloy/tools/alloy-cli/` (the first-cut
  scaffolder we are superseding) so we don't fork-and-diverge.

This proposal does **only that**.  No commands beyond `alloy
--version`.  No TUI.  No MCP.  Subsequent proposals build on this.

## What Changes

- Package skeleton:
  - `pyproject.toml` (hatchling + hatch-vcs, `[project.scripts] alloy
    = "alloy_cli.main:main"`)
  - `src/alloy_cli/__init__.py`, `src/alloy_cli/main.py` stubs
  - `tests/` directory with the smoke test
- License: dual MIT / Apache-2.0 (matches the rest of the Alloy
  ecosystem's intended licensing).  `LICENSE-MIT` + `LICENSE-APACHE`
  files at the repo root.
- CI scaffold (`.github/workflows/ci.yml`):
  - matrix on Python 3.11 / 3.12 / 3.13
  - `ruff check`
  - `pyright src/alloy_cli`
  - `pytest -q`
- Code style (`ruff` + `pyright` configs in `pyproject.toml`).
- `alloy --version` command (the only working command in this proposal)
  reading from `alloy_cli._version` (hatch-vcs-generated).
- Migration entry in the parent project's tracker noting that
  `alloy/tools/alloy-cli/` will be deprecated in a follow-up
  (`integrate-data-sources` ports the existing logic; a separate
  alloy-side change deprecates the in-tree copy).

## Impact

- New repo, no existing consumers.
- `pip install alloy-cli` works; `alloy --version` prints a version.
- CI is green on day one.
- Foundation for every later proposal — `integrate-data-sources`,
  `define-project-format`, `add-cli-*`, `add-tui-*`, `add-mcp-server`.

## What this DOES NOT do

- No commands beyond `--version` / `--help`.  Stub `main.py` exits
  with an informative message pointing at the OpenSpec roadmap.
- No data integration.  alloy-devices-yml is not yet read.
- No TUI.  Textual is in dependencies but unused.
- No MCP.
- No `alloy/tools/alloy-cli/` deletion in this PR.  That's a
  separate alloy-side change after Phase 2 reaches feature parity.
