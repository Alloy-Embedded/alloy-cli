# Tasks — bootstrap-alloy-cli

## Phase 1: Package skeleton

- [x] 1.1 `pyproject.toml` with hatchling + hatch-vcs, `[project]`
      block, `[project.scripts] alloy = "alloy_cli.main:main"`,
      `[project.optional-dependencies] dev` and `mcp` groups.
- [x] 1.2 `src/alloy_cli/__init__.py` exporting `__version__` from
      `_version.py` (hatch-vcs-generated).
- [x] 1.3 `src/alloy_cli/main.py` with a Click root command.

## Phase 2: License + governance

- [x] 2.1 `LICENSE-MIT` and `LICENSE-APACHE` at repo root.
- [x] 2.2 `pyproject.toml` `license = { text = "MIT OR Apache-2.0" }`.
- [x] 2.3 README license section pointing at both files.

## Phase 3: CI scaffold

- [x] 3.1 `.github/workflows/ci.yml` matrix (3.11 / 3.12 / 3.13),
      `ruff check`, `ruff format --check`, `pyright src/alloy_cli`,
      `pytest -q`, openspec validate --strict.
- [x] 3.2 `.github/workflows/release.yml` building wheel + sdist on
      tag, publishing to PyPI via trusted publishing.
- [x] 3.3 Pre-commit config (`ruff format`, `ruff check --fix`).

## Phase 4: Smoke test

- [x] 4.1 `tests/test_version.py`: `alloy --version` exits 0 and
      prints a non-empty version string.
- [x] 4.2 `tests/test_help.py`: `alloy --help` exits 0 and mentions
      "Alloy embedded platform".

## Phase 5: Spec + final checks

- [x] 5.1 Spec delta in `specs/cli-surface/spec.md`.
- [x] 5.2 `openspec validate bootstrap-alloy-cli --strict` passes.
- [x] 5.3 `pytest -q` clean (4 passed locally; CI matrix covers
      three Python versions).
- [x] 5.4 README license section points at both license files.
