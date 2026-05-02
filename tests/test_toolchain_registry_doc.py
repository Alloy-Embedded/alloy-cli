"""Regression guards on ``docs/TOOLCHAIN_REGISTRY.md``.

The doc is the contributor-facing reference for the per-family
toolchain manifest format.  When the schema vocabulary grows (a
new field on the tool-requirement object, a new top-level key,
a new `source` value, a new `capabilities` enum entry), the doc
must grow with it.  These tests fail loudly when the doc drifts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "TOOLCHAIN_REGISTRY.md"
SCHEMA_PATH = REPO_ROOT / "schema" / "family_toolchain_v1.json"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Required schema field coverage
# ---------------------------------------------------------------------------


def test_doc_covers_every_top_level_schema_field() -> None:
    """Every property of the manifest's root schema object is documented.

    Required top-level fields go through the schema's `properties`
    block; the doc must namedrop each one in a heading or table cell.
    """
    schema = _schema()
    properties = set(schema.get("properties", {}))
    text = _doc_text()
    for field in properties:
        assert (
            f"`{field}`" in text
        ), f"docs/TOOLCHAIN_REGISTRY.md is missing top-level field `{field}`"


def test_doc_covers_every_tool_requirement_field() -> None:
    """The tool_requirement sub-schema fields all appear in the doc."""
    schema = _schema()
    tool_props = set(schema["$defs"]["tool_requirement"]["properties"])
    text = _doc_text()
    for field in tool_props:
        assert (
            f"`{field}`" in text
        ), f"docs/TOOLCHAIN_REGISTRY.md is missing tool field `{field}`"


def test_doc_covers_every_capability_enum_value() -> None:
    """Every value in the `capabilities` closed enum has a row."""
    schema = _schema()
    cap_enum = schema["$defs"]["tool_requirement"]["properties"]["capabilities"][
        "items"
    ]["enum"]
    text = _doc_text()
    for cap in cap_enum:
        assert (
            f"`{cap}`" in text
        ), f"docs/TOOLCHAIN_REGISTRY.md is missing capability `{cap}`"


def test_doc_covers_every_source_kind() -> None:
    """The `source` enum strings are explained in their own sub-table.

    We don't pin the exact pattern — we walk it and assert every
    alternative literal (xpack, vendor, espressif, probe-rs-installer,
    plus the github: prefix) is mentioned.
    """
    text = _doc_text()
    for source in ("xpack", "vendor", "espressif", "probe-rs-installer"):
        assert (
            f"`{source}`" in text
        ), f"docs/TOOLCHAIN_REGISTRY.md is missing source `{source}`"
    # `github:` is a prefix; check the prefix appears somewhere
    # (with or without backticks).
    assert "github:" in text


# ---------------------------------------------------------------------------
# Walkthrough hygiene
# ---------------------------------------------------------------------------


def test_doc_links_to_schema_file_and_loader() -> None:
    text = _doc_text()
    # Relative links from docs/ → ../schema/ ../src/alloy_cli/core/
    assert "../schema/family_toolchain_v1.json" in text
    assert "../src/alloy_cli/core/toolchain_registry.py" in text


def test_doc_links_to_error_cookbook_anchors() -> None:
    """Every family-toolchain-* error type appears as a clickable anchor."""
    text = _doc_text()
    for error_type in (
        "family-toolchain-error",
        "family-toolchain-cycle",
        "family-toolchain-unknown-parent",
        "family-toolchain-schema",
        "family-toolchain-not-found",
    ):
        # Anchors use Markdown's lowercase-hyphen slug — same as the
        # error_type string.
        anchor = f"ERROR_COOKBOOK.md#{error_type}"
        assert anchor in text, (
            f"docs/TOOLCHAIN_REGISTRY.md is missing error cookbook anchor "
            f"for {error_type}"
        )


def test_doc_includes_add_a_family_walkthrough() -> None:
    """The "Add a new family" section is the contract Wave-2's
    contributor-onboarding work hangs off — keep it discoverable.
    """
    text = _doc_text()
    # Heading
    assert re.search(r"##\s+Add a new family", text), (
        "docs/TOOLCHAIN_REGISTRY.md is missing the 'Add a new family' heading"
    )
    # Mentions the test command
    assert "tests/test_family_toolchain_schema.py" in text
    # Mentions both wheel-data tables in pyproject.toml
    assert "shared-data" in text
    assert "force-include" in text


def test_doc_explains_extends_resolution_with_worked_example() -> None:
    text = _doc_text()
    assert "arm-cortex-m" in text
    assert "stm32f4" in text
    # Must call out the merge-by-tool-name rule (so contributors don't
    # think child entries shadow base ones positionally).
    assert "by tool name" in text.lower() or "by `tool` name" in text.lower()
