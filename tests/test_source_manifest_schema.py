"""Tests for ``schema/source_manifest_v1.json`` and the shipped pin files.

Wave-2 group 1 ships only the schema + four pin files.  These tests
validate the schema directly so a regression in either the schema
constraints OR a shipped JSON surfaces in CI before any code in
``core.tool_sources`` is even imported.

SHA256 fields in the shipped pins are zero-padded placeholders
(`_pending_verification: true`); group 8 ships
``scripts/refresh_source_pins.py`` to populate them from upstream
release feeds.  The schema enforces the 64-hex-char shape on every
sha256, so the placeholder still exercises the regex.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "source_manifest_v1.json"
SOURCES_DIR = REPO_ROOT / "data" / "sources"

SHIPPED_SOURCES: tuple[str, ...] = (
    "xpack",
    "github",
    "probe-rs",
    "espressif",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _zero_sha() -> str:
    return "0" * 64


def _valid_pin_file() -> dict[str, Any]:
    """Hand-rolled minimum manifest used as the baseline for negative fixtures."""
    return {
        "schema_version": "1.0.0",
        "source": "github",
        "_pending_verification": True,
        "tools": [
            {
                "tool": "tio",
                "version": "2.7",
                "hosts": {
                    "linux-x86_64": {
                        "url": "https://example.com/tio-linux.tar.gz",
                        "sha256": _zero_sha(),
                        "archive_kind": "tar.gz",
                        "binaries": ["bin/tio"],
                    }
                },
            }
        ],
    }


def _all_shipped_paths() -> Iterator[Path]:
    for name in SHIPPED_SOURCES:
        yield SOURCES_DIR / f"{name}.json"


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_schema_file_exists_and_is_draft_2020_12() -> None:
    assert SCHEMA_PATH.exists(), f"schema file missing at {SCHEMA_PATH}"
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("/2020-12/schema")
    assert schema["title"].startswith("alloy-cli")


def test_baseline_pin_file_validates(validator: Draft202012Validator) -> None:
    errors = sorted(validator.iter_errors(_valid_pin_file()), key=lambda e: list(e.path))
    assert errors == [], f"baseline must validate; got {[e.message for e in errors]}"


# ---------------------------------------------------------------------------
# Shipped pin files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source_path", list(_all_shipped_paths()), ids=lambda p: p.stem)
def test_shipped_pin_file_validates(
    source_path: Path, validator: Draft202012Validator
) -> None:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert errors == [], (
        f"{source_path.name} failed schema validation:\n"
        + "\n".join(
            f"  • /{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
            for e in errors
        )
    )


@pytest.mark.parametrize("source_path", list(_all_shipped_paths()), ids=lambda p: p.stem)
def test_shipped_pin_filename_matches_source_field(source_path: Path) -> None:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    assert payload["source"] == source_path.stem, (
        f"{source_path.name} declares source={payload['source']!r} but lives "
        f"at {source_path.stem}.json"
    )


def test_every_shipped_source_has_a_pin_file() -> None:
    actual = sorted(p.stem for p in SOURCES_DIR.glob("*.json"))
    assert actual == sorted(SHIPPED_SOURCES), (
        f"data/sources/ contents drifted from SHIPPED_SOURCES: "
        f"on disk={actual}, expected={sorted(SHIPPED_SOURCES)}"
    )


def test_every_shipped_pin_file_carries_pending_verification() -> None:
    """Until refresh_source_pins.py runs, every pin file MUST flag itself
    as pending so the installer (group 3) can refuse to download.

    This test will need to be relaxed (or removed) once group 8's
    refresh script populates real SHAs.
    """
    for path in _all_shipped_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("_pending_verification") is True, (
            f"{path.name} must declare _pending_verification: true while "
            "sha256 fields remain placeholders"
        )


def test_placeholder_sha_is_zero_padded() -> None:
    """A pin file with `_pending_verification: true` SHOULD use the
    canonical zero-padded sha256 placeholder so reviewers can grep
    for it."""
    for path in _all_shipped_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("_pending_verification") is not True:
            continue
        for tool in payload["tools"]:
            for host_id, artefact in tool["hosts"].items():
                assert artefact["sha256"] == _zero_sha(), (
                    f"{path.name} {tool['tool']!r} {host_id} sha256 should "
                    f"be the zero-padded placeholder while pending verification"
                )


# ---------------------------------------------------------------------------
# Cross-file invariants
# ---------------------------------------------------------------------------


def test_xpack_covers_arm_gcc_cmake_ninja() -> None:
    """The Cortex-M base manifest in Wave 1 declares these three tools
    as required; xpack.json must have a matching pin for each.
    """
    payload = json.loads((SOURCES_DIR / "xpack.json").read_text(encoding="utf-8"))
    tool_names = {t["tool"] for t in payload["tools"]}
    assert {"arm-none-eabi-gcc", "cmake", "ninja"} <= tool_names


def test_probe_rs_carries_udev_rules() -> None:
    """probe-rs is the only tool we currently know needs udev rules; the
    rules text must be embedded in the pin file (we can't ship them as
    a separate download).
    """
    payload = json.loads((SOURCES_DIR / "probe-rs.json").read_text(encoding="utf-8"))
    probe_rs = next(t for t in payload["tools"] if t["tool"] == "probe-rs")
    rules = probe_rs.get("udev_rules", "")
    assert "ATTRS{idVendor}" in rules, "udev_rules content does not look like rules"
    assert "/etc/udev/rules.d" in rules, "udev_rules should mention the rules dir"


def test_espressif_does_not_ship_arm_gcc() -> None:
    """Espressif pins are Xtensa / RISC-V only — arm-none-eabi-gcc lives
    in xpack.json (single source of truth per tool)."""
    payload = json.loads((SOURCES_DIR / "espressif.json").read_text(encoding="utf-8"))
    tool_names = {t["tool"] for t in payload["tools"]}
    assert "arm-none-eabi-gcc" not in tool_names
    assert "xtensa-esp-elf-gcc" in tool_names
    assert "riscv32-esp-elf-gcc" in tool_names


def test_hosts_cover_at_least_macos_arm64_for_every_tool() -> None:
    """Apple Silicon is the platform the project author and most
    contributors run.  Every shipped tool must have a macos-arm64 pin
    OR explicitly declare it in unsupported_hosts.
    """
    for path in _all_shipped_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for tool in payload["tools"]:
            host_keys = set(tool["hosts"])
            unsupported = set(tool.get("unsupported_hosts") or ())
            assert "macos-arm64" in host_keys or "macos-arm64" in unsupported, (
                f"{path.name} {tool['tool']!r} has no macos-arm64 pin and "
                "doesn't declare it in unsupported_hosts"
            )


def test_no_vendor_source_in_any_pin_file() -> None:
    """Vendor-source tools are EULA-gated and Wave 1's renderer owns
    them; they must NEVER appear in data/sources/*.json."""
    for path in _all_shipped_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["source"] != "vendor", (
            f"{path.name} declares source=vendor — vendor tools must not "
            "appear in source pin files"
        )


# ---------------------------------------------------------------------------
# Negative fixtures
# ---------------------------------------------------------------------------


def test_missing_schema_version_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    del payload["schema_version"]
    assert list(validator.iter_errors(payload))


def test_missing_source_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    del payload["source"]
    assert list(validator.iter_errors(payload))


def test_unknown_source_value_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["source"] = "homebrew"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_vendor_source_is_rejected(validator: Draft202012Validator) -> None:
    """The schema's `source` enum must NOT include `vendor`."""
    payload = _valid_pin_file()
    payload["source"] = "vendor"
    errors = list(validator.iter_errors(payload))
    assert errors, "vendor source must fail the enum check"


def test_unknown_archive_kind_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["archive_kind"] = "rar"
    assert list(validator.iter_errors(payload))


def test_short_sha256_fails(validator: Draft202012Validator) -> None:
    """Anything other than 64 hex chars must fail the regex."""
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["sha256"] = "abc123"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_uppercase_sha256_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["sha256"] = "A" * 64
    errors = list(validator.iter_errors(payload))
    assert errors, "sha256 must be lower-case hex"


def test_unknown_host_triple_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["solaris-sparc64"] = payload["tools"][0]["hosts"][
        "linux-x86_64"
    ].copy()
    errors = list(validator.iter_errors(payload))
    assert errors


def test_empty_hosts_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"] = {}
    errors = list(validator.iter_errors(payload))
    assert errors, "minProperties=1 should reject empty host map"


def test_empty_binaries_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["binaries"] = []
    errors = list(validator.iter_errors(payload))
    assert errors


def test_absolute_binary_path_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["binaries"] = ["/abs/path"]
    errors = list(validator.iter_errors(payload))
    assert errors, "binaries entries must be relative paths"


def test_additional_root_property_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["spurious"] = "x"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_additional_tool_property_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["spurious"] = "x"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_additional_host_artifact_property_fails(
    validator: Draft202012Validator,
) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["spurious"] = "x"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_http_url_rejected(validator: Draft202012Validator) -> None:
    """Only https:// URLs are allowed."""
    payload = _valid_pin_file()
    payload["tools"][0]["hosts"]["linux-x86_64"]["url"] = "http://example.com/x.tar.gz"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_bad_version_pattern_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"][0]["version"] = "latest"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_empty_tools_array_fails(validator: Draft202012Validator) -> None:
    payload = _valid_pin_file()
    payload["tools"] = []
    errors = list(validator.iter_errors(payload))
    assert errors, "tools must declare at least one entry (minItems=1)"


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------


def test_valid_pin_file_helper_is_isolated() -> None:
    a = _valid_pin_file()
    b = _valid_pin_file()
    a["tools"][0]["tool"] = "mutated"
    assert b["tools"][0]["tool"] != "mutated"
    assert _valid_pin_file() == copy.deepcopy(_valid_pin_file())
