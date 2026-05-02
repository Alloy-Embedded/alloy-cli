# Releasing alloy-cli

This document is the runbook for cutting a public release.
Workflow: tag → CI verifies → PyPI publishes → CHANGELOG seals
the entry.

## Prerequisites

- Maintainer access to <https://github.com/Alloy-Embedded/alloy-cli>.
- PyPI **trusted publisher** configured for the project (no
  long-lived API token; OIDC handles authentication via
  GitHub Actions).  See PyPI → project → *Publishing* tab.
- A clean working tree on `main`, all CI green.
- Local checkout updated with `git pull --ff-only`.

## Pre-flight

1. Confirm the suite passes locally:
   ```bash
   uv run pytest -q
   uv run ruff check src tests
   uv run pyright src tests
   ```
2. Confirm OpenSpec is happy:
   ```bash
   openspec validate --all --strict
   ```
3. Refresh the docs gallery if any TUI screen drifted:
   ```bash
   uv run pytest tests/test_snapshots.py --snapshot-update
   uv run python scripts/generate_docs_images.py
   ```
   The two outputs must stay byte-stable; the snapshot test will
   tell you if they don't.

## Cutting the release

1. Pick the version: ``MAJOR.MINOR.PATCH`` per SemVer.  Wave-1
   shipped at ``0.1.0``; the wave-2 batch ships at ``0.2.0``.
2. Update `CHANGELOG.md`:
   - Move every Unreleased bullet under the new version
     header.
   - Re-add the empty Unreleased section at the top.
   - Update the bottom-of-file compare links.
3. Commit + push the CHANGELOG bump:
   ```bash
   git checkout -b release/vX.Y.Z
   git add CHANGELOG.md
   git commit -m "Release vX.Y.Z"
   git push -u origin release/vX.Y.Z
   gh pr create --title "Release vX.Y.Z" --body "See CHANGELOG.md"
   ```
4. Once the PR is reviewed and merged, tag from `main`:
   ```bash
   git checkout main
   git pull --ff-only
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

## Workflow gates

Pushing the tag fires `.github/workflows/release.yml`:

1. **Build**: `python -m build` produces ``dist/*.whl`` and
   ``dist/*.tar.gz``.
2. **Smoke**: the workflow installs the freshly-built wheel into
   a clean venv and asserts `alloy --version` exits cleanly.  A
   non-zero exit code blocks the publish step.
3. **HIL** (`.github/workflows/hil.yml`): runs on the self-hosted
   runner pool — scaffolds + builds `nucleo_g071rb` and asserts
   the ELF lands under `.alloy/build/`.  A failure here also
   blocks the publish (the release job depends on the HIL job).
4. **Publish**: `pypa/gh-action-pypi-publish` uploads to PyPI via
   trusted publishing.

If anything fails:
- Investigate via the GitHub Actions log.
- Delete the tag remotely (`git push origin :refs/tags/vX.Y.Z`)
  and locally, fix the issue, re-tag.
- The smoke job is intentionally minimal — anything beyond
  `alloy --version` belongs in `tests/`.

## After the release

1. Verify on PyPI: <https://pypi.org/project/alloy-cli/>.
2. Verify the GitHub release page got auto-populated by
   `gh release view`.
3. Bump the post-release version in `CHANGELOG.md` (start a
   fresh **Unreleased** section), commit, push.
4. Announce in the project's README or discussions, if needed.

## Self-hosted HIL runner setup

The HIL workflow needs a self-hosted runner with the embedded
toolchain installed.  Tag the runner with `hil` so only HIL
jobs target it.  Minimum software:

- `arm-none-eabi-gcc` 14+ on PATH
- `cmake` 3.27+
- `ninja` 1.11+
- `probe-rs` 0.24+
- A stable Python install (the workflow installs `uv` per run)

Hardware setup is currently a single Nucleo-G071RB attached via
ST-Link on `/dev/ttyACM0`.  The runner script asserts the probe
is detected before running the build but does not flash hardware
(the test only verifies the cross-compile pipeline).
