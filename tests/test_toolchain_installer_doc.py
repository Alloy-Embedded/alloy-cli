"""Regression guards on ``docs/TOOLCHAIN_INSTALLER.md``.

The doc is the contributor-facing reference for the per-source pin
file format + the content-addressed store + the trust model.  When
the schema vocabulary grows (a new field on the host artefact, a
new source kind, a new error type), the doc must grow with it.
These tests fail loudly when the doc drifts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "TOOLCHAIN_INSTALLER.md"
SCHEMA_PATH = REPO_ROOT / "schema" / "source_manifest_v1.json"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Schema field coverage
# ---------------------------------------------------------------------------


def test_doc_covers_every_top_level_pin_file_field() -> None:
    schema = _schema()
    properties = set(schema.get("properties", {}))
    text = _doc_text()
    # ``_pending_verification`` and ``_notes`` are optional but documented;
    # require them too.
    expected = properties | {"_pending_verification", "_notes"}
    for field in expected:
        assert (
            f"`{field}`" in text
        ), f"docs/TOOLCHAIN_INSTALLER.md is missing pin-file field `{field}`"


def test_doc_covers_every_tool_pin_field() -> None:
    schema = _schema()
    tool_props = set(schema["$defs"]["tool_pin"]["properties"])
    text = _doc_text()
    for field in tool_props:
        assert (
            f"`{field}`" in text
        ), f"docs/TOOLCHAIN_INSTALLER.md is missing tool-pin field `{field}`"


def test_doc_covers_every_host_artefact_field() -> None:
    schema = _schema()
    artefact_props = set(schema["$defs"]["host_artifact"]["properties"])
    text = _doc_text()
    for field in artefact_props:
        assert (
            f"`{field}`" in text
        ), f"docs/TOOLCHAIN_INSTALLER.md is missing host-artefact field `{field}`"


def test_doc_covers_every_archive_kind() -> None:
    schema = _schema()
    enum = schema["$defs"]["host_artifact"]["properties"]["archive_kind"]["enum"]
    text = _doc_text()
    for kind in enum:
        assert (
            f"`{kind}`" in text
        ), f"docs/TOOLCHAIN_INSTALLER.md is missing archive_kind `{kind}`"


def test_doc_covers_every_source_kind() -> None:
    schema = _schema()
    enum = schema["properties"]["source"]["enum"]
    text = _doc_text()
    for source in enum:
        assert (
            f"`{source}`" in text
        ), f"docs/TOOLCHAIN_INSTALLER.md is missing source kind `{source}`"


# ---------------------------------------------------------------------------
# Cookbook anchors
# ---------------------------------------------------------------------------


def test_doc_links_to_every_installer_error_anchor() -> None:
    """Every family-toolchain-installer-* error type from
    ``core.errors`` must appear as a clickable cookbook anchor in
    the contributor doc.
    """
    text = _doc_text()
    expected_errors = (
        "family-toolchain-installer-error",
        "family-toolchain-installer-checksum",
        "family-toolchain-installer-download",
        "family-toolchain-installer-extract",
        "family-toolchain-installer-store-corrupt",
        "family-toolchain-installer-version-mismatch",
        "family-toolchain-installer-unsupported-host",
        "family-toolchain-installer-locked",
    )
    for error_type in expected_errors:
        anchor = f"ERROR_COOKBOOK.md#{error_type}"
        assert anchor in text, (
            f"docs/TOOLCHAIN_INSTALLER.md is missing cookbook anchor "
            f"for {error_type}"
        )


# ---------------------------------------------------------------------------
# Cross-links
# ---------------------------------------------------------------------------


def test_doc_links_to_wave1_registry_doc() -> None:
    text = _doc_text()
    assert "TOOLCHAIN_REGISTRY.md" in text


def test_doc_links_to_schema_files() -> None:
    text = _doc_text()
    assert "../schema/source_manifest_v1.json" in text
    assert "../schema/family_toolchain_v1.json" in text


def test_doc_links_to_implementation_modules() -> None:
    text = _doc_text()
    assert "../src/alloy_cli/core/tool_sources.py" in text
    assert "../src/alloy_cli/core/toolchain_manager.py" in text
    assert "../src/alloy_cli/core/lockfile_toolchain.py" in text
    assert "../src/alloy_cli/commands/toolchain.py" in text


# ---------------------------------------------------------------------------
# Walkthrough hygiene
# ---------------------------------------------------------------------------


def test_doc_includes_add_a_source_walkthrough() -> None:
    text = _doc_text()
    assert re.search(r"##\s+Add a new source", text), (
        "docs/TOOLCHAIN_INSTALLER.md is missing the 'Add a new source' heading"
    )
    # Mentions the right test commands
    assert "tests/test_source_manifest_schema.py" in text
    assert "tests/test_tool_sources.py" in text


def test_doc_documents_refresh_script() -> None:
    text = _doc_text()
    assert "refresh_source_pins.py" in text
    assert "--apply" in text
    assert "--dry-run" in text or "dry-run" in text.lower()


def test_doc_calls_out_trust_boundaries() -> None:
    """The three trust boundaries (pin files / download / extraction)
    are the security contract for Wave 2 — must be documented
    explicitly so reviewers know what to inspect."""
    text = _doc_text()
    assert "Trust model" in text or "trust model" in text.lower()
    assert "pin files" in text.lower()
    assert "tarfile.data_filter" in text


def test_doc_explains_store_layout() -> None:
    text = _doc_text()
    assert "platformdirs.user_data_dir" in text
    assert "store/<sha256>" in text
    assert "by-name/<tool>/<version>" in text
    assert "manifest.json" in text


def test_doc_documents_lockfile_format() -> None:
    text = _doc_text()
    assert ".alloy/toolchain.lock" in text
    assert "schema_version" in text


def test_doc_documents_cmake_toolchain_file_generation() -> None:
    text = _doc_text()
    assert "toolchain.cmake" in text
    assert "CMAKE_TOOLCHAIN_FILE" in text
    assert "CMAKE_C_COMPILER" in text


def test_doc_documents_udev_rules_handling() -> None:
    text = _doc_text()
    assert "udev" in text.lower()
    assert "sudo" in text.lower()
    assert "never invokes sudo" in text.lower() or "never invokes" in text.lower()
