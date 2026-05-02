# Tasks — bootstrap-alloy-cli

## Phase 1: Package skeleton

- [ ] 1.1 `pyproject.toml` with hatchling + hatch-vcs, `[project]`
      block, `[project.scripts] alloy = "alloy_cli.main:main"`,
      `[project.optional-dependencies] dev` and `mcp` groups.
- [ ] 1.2 `src/alloy_cli/__init__.py` exporting `__version__` from
      `_version.py` (hatch-vcs-generated).
- [ ] 1.3 `src/alloy_cli/main.py` with a stub `main()` that prints
      "alloy-cli not yet implemented; see openspec/changes/" and
      exits 2.

## Phase 2: License + governance

- [ ] 2.1 `LICENSE-MIT` and `LICENSE-APACHE` at repo root.
- [ ] 2.2 `pyproject.toml` `license = { text = "MIT OR
      Apache-2.0" }`.
- [ ] 2.3 README license section pointing at both files.

## Phase 3: CI scaffold

- [ ] 3.1 `.github/workflows/ci.yml` matrix (3.11 / 3.12 / 3.13),
      `ruff check`, `pyright src/alloy_cli`, `pytest -q`.
- [ ] 3.2 `.github/workflows/release.yml` building wheel + sdist on
      tag, publishing to PyPI.
- [ ] 3.3 Pre-commit config (`ruff format`, `ruff check --fix`).

## Phase 4: Smoke test

- [ ] 4.1 `tests/test_version.py`: `alloy --version` exits 0 and
      prints a non-empty version string.
- [ ] 4.2 `tests/test_help.py`: `alloy --help` exits 0 and mentions
      "Alloy embedded platform".

## Phase 5: Spec + final checks

- [ ] 5.1 Spec delta in `specs/cli-surface/spec.md` capturing the
      `--version` / `--help` minimum surface.
- [ ] 5.2 `openspec validate bootstrap-alloy-cli --strict` passes.
- [ ] 5.3 `pytest -q` clean on three Python versions.
- [ ] 5.4 README badges (CI, PyPI version) updated.
