"""Regression guard: ``mkdocs build --strict`` succeeds.

Wave-5's docs site (`add-docs-site` capability) depends on every
contributor's commit producing a buildable site.  This test
spawns the build in a tmpdir and asserts:

  * exit code 0
  * no warnings emitted (mkdocs strict already turns warnings into
    errors, but we double-check the captured stderr just in case)
  * `site/index.html` lands

Marked with ``@pytest.mark.docs`` so contributors who haven't
installed ``pip install -e .[docs]`` get a SKIP rather than an
import-error noise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"


pytestmark = pytest.mark.docs


def _mkdocs_available() -> bool:
    """Return True iff the `mkdocs` CLI is on PATH."""
    return shutil.which("mkdocs") is not None


@pytest.mark.skipif(
    not _mkdocs_available(),
    reason="`mkdocs` not installed; run `pip install -e .[docs]`",
)
def test_mkdocs_build_strict_succeeds(tmp_path: Path) -> None:
    """The strict build emits exit 0 with no errors."""
    site_dir = tmp_path / "site"
    env = {**os.environ, "DISABLE_MKDOCS_2_WARNING": "true"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(MKDOCS_YML),
            "--site-dir",
            str(site_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "mkdocs build --strict failed:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    # Strict mode turns WARNING into a non-zero exit.  Assert it
    # explicitly anyway so a future relaxation is loud.
    combined = (result.stdout + result.stderr).lower()
    assert "aborted" not in combined, (
        f"mkdocs --strict aborted with warnings:\n{combined}"
    )


@pytest.mark.skipif(
    not _mkdocs_available(),
    reason="`mkdocs` not installed; run `pip install -e .[docs]`",
)
def test_strict_build_produces_landing_page(tmp_path: Path) -> None:
    """The build SHALL produce site/index.html with the project tagline."""
    site_dir = tmp_path / "site"
    env = {**os.environ, "DISABLE_MKDOCS_2_WARNING": "true"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(MKDOCS_YML),
            "--site-dir",
            str(site_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        timeout=120,
    )
    index = site_dir / "index.html"
    assert index.exists(), "site/index.html missing after build"
    body = index.read_text(encoding="utf-8")
    # Tagline from docs/index.md:
    assert "Embedded firmware development without the IDE" in body
    # Install one-liner — pygments wraps tokens in <span class="w">
    # spans for whitespace highlighting, so strip tags before
    # matching.
    import re

    text_only = re.sub(r"<[^>]+>", "", body)
    assert "pip install alloy-cli" in text_only


@pytest.mark.skipif(
    not _mkdocs_available(),
    reason="`mkdocs` not installed; run `pip install -e .[docs]`",
)
def test_cli_reference_renders_every_alloy_verb(tmp_path: Path) -> None:
    """The auto-generated CLI reference page lists every `alloy <verb>`
    registered on `alloy_cli.main:cli`."""
    site_dir = tmp_path / "site"
    env = {**os.environ, "DISABLE_MKDOCS_2_WARNING": "true"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(MKDOCS_YML),
            "--site-dir",
            str(site_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        timeout=120,
    )
    cli_page = site_dir / "reference" / "cli" / "index.html"
    assert cli_page.exists()
    body = cli_page.read_text(encoding="utf-8")
    expected = (
        "alloy add",
        "alloy boards",
        "alloy build",
        "alloy doctor",
        "alloy erase",
        "alloy flash",
        "alloy mcp",
        "alloy monitor",
        "alloy new",
        "alloy reset",
        "alloy setup",
        "alloy toolchain",
        "alloy ui",
    )
    for verb in expected:
        assert verb in body, (
            f"CLI reference is missing `{verb}` — every Click command "
            "registered on `alloy_cli.main:cli` must surface."
        )


@pytest.mark.skipif(
    not _mkdocs_available(),
    reason="`mkdocs` not installed; run `pip install -e .[docs]`",
)
def test_api_reference_renders_orchestrator_symbols(tmp_path: Path) -> None:
    """The API reference for `toolchain_orchestrator` includes every
    public symbol — auto-generated from docstrings."""
    site_dir = tmp_path / "site"
    env = {**os.environ, "DISABLE_MKDOCS_2_WARNING": "true"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(MKDOCS_YML),
            "--site-dir",
            str(site_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        timeout=120,
    )
    page = site_dir / "api" / "toolchain-orchestrator" / "index.html"
    assert page.exists()
    body = page.read_text(encoding="utf-8")
    # The sealed `InstallEvent` union + the public dataclasses.
    expected = (
        "install_family",
        "ToolStarted",
        "ToolDownloaded",
        "ToolInstalled",
        "ToolFailed",
        "ToolSkippedVendor",
        "ToolSkippedHostUnsupported",
        "InstallOutcome",
        "InstallReport",
    )
    for symbol in expected:
        assert symbol in body, (
            f"API reference is missing `{symbol}` — every public symbol "
            "in `toolchain_orchestrator.__all__` must surface."
        )


@pytest.mark.skipif(
    not _mkdocs_available(),
    reason="`mkdocs` not installed; run `pip install -e .[docs]`",
)
def test_api_reference_renders_probe_orchestrator_symbols(tmp_path: Path) -> None:
    """Mirror of the above for the Wave-4 probe orchestrator."""
    site_dir = tmp_path / "site"
    env = {**os.environ, "DISABLE_MKDOCS_2_WARNING": "true"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(MKDOCS_YML),
            "--site-dir",
            str(site_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        timeout=120,
    )
    page = site_dir / "api" / "probe-orchestrator" / "index.html"
    assert page.exists()
    body = page.read_text(encoding="utf-8")
    expected = (
        "select_probe",
        "reset_target",
        "plan_erase",
        "execute_erase",
        "open_monitor",
        "real_probe_for",
        "ProbeIdentity",
        "MonitorOpened",
        "MonitorBytes",
        "MonitorClosed",
        "MonitorSessionTable",
    )
    for symbol in expected:
        assert symbol in body, (
            f"API reference is missing `{symbol}`"
        )
