"""Tests for ``schema/family_toolchain_v1.json`` and the shipped manifests.

Wave-1 of the toolchain-management track ships only the schema +
manifest data; the parser module lands in task block 2.  These tests
exercise the schema directly via :mod:`jsonschema` so a regression
in either the schema constraints OR a shipped YAML surfaces in CI
before any code in ``core.toolchain_registry`` is even imported.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "family_toolchain_v1.json"
FAMILIES_DIR = REPO_ROOT / "data" / "families"

SHIPPED_FAMILIES: tuple[str, ...] = (
    "arm-cortex-m",
    "stm32f4",
    "stm32g0",
    "rp2040",
    "nrf52",
    "esp32",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _valid_manifest() -> dict[str, Any]:
    """Hand-rolled manifest used as the baseline for negative fixtures."""
    return {
        "schema_version": "1.0.0",
        "family_id": "samd51",
        "core": "cortex-m4f",
        "arch": "armv7em",
        "extends": "arm-cortex-m",
        "required": [
            {
                "tool": "bossac",
                "version": ">=1.9",
                "source": "github:shumatech/BOSSA",
                "capabilities": ["flash"],
            }
        ],
        "recommended": [
            {
                "tool": "Atmel-Studio",
                "version": ">=7.0",
                "source": "vendor",
                "capabilities": ["debug", "register-debug"],
                "install_docs": {
                    "windows": "https://www.microchip.com/en-us/tools-resources/develop/microchip-studio"
                },
            }
        ],
    }


def _all_shipped_paths() -> Iterator[Path]:
    for family_id in SHIPPED_FAMILIES:
        yield FAMILIES_DIR / f"{family_id}.yml"


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_schema_file_exists_and_is_draft_2020_12(validator: Draft202012Validator) -> None:
    # Re-read from disk so we exercise the file the wheel ships, and
    # so Pyright sees a concrete dict (validator.schema is typed as
    # ``bool | Mapping`` because JSON Schema technically allows ``true``
    # / ``false`` as a schema literal).
    assert SCHEMA_PATH.exists(), f"schema file missing at {SCHEMA_PATH}"
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("/2020-12/schema")
    assert schema["title"].startswith("alloy-cli")
    # Sanity: the validator's schema is the same payload we just loaded.
    assert validator.schema == schema


def test_baseline_manifest_validates(validator: Draft202012Validator) -> None:
    errors = sorted(validator.iter_errors(_valid_manifest()), key=lambda e: list(e.path))
    assert errors == [], f"baseline manifest must validate; got {[e.message for e in errors]}"


# ---------------------------------------------------------------------------
# Shipped manifests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family_path", list(_all_shipped_paths()), ids=lambda p: p.stem)
def test_shipped_manifest_validates(
    family_path: Path, validator: Draft202012Validator
) -> None:
    payload = yaml.safe_load(family_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{family_path} did not parse as a YAML mapping"
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert errors == [], (
        f"{family_path.name} failed schema validation:\n"
        + "\n".join(f"  • /{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors)
    )


@pytest.mark.parametrize("family_path", list(_all_shipped_paths()), ids=lambda p: p.stem)
def test_shipped_manifest_filename_matches_family_id(family_path: Path) -> None:
    payload = yaml.safe_load(family_path.read_text(encoding="utf-8"))
    assert payload["family_id"] == family_path.stem, (
        f"{family_path.name} declares family_id={payload['family_id']!r} "
        f"but lives at {family_path.stem}.yml"
    )


def test_every_shipped_family_has_a_manifest() -> None:
    actual = sorted(p.stem for p in FAMILIES_DIR.glob("*.yml"))
    assert actual == sorted(SHIPPED_FAMILIES), (
        f"data/families/ contents drifted from SHIPPED_FAMILIES: "
        f"on disk={actual}, expected={sorted(SHIPPED_FAMILIES)}"
    )


# ---------------------------------------------------------------------------
# Negative fixtures
# ---------------------------------------------------------------------------


def test_missing_schema_version_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    del payload["schema_version"]
    errors = list(validator.iter_errors(payload))
    assert errors, "manifest without schema_version must fail validation"
    assert any("schema_version" in err.message for err in errors)


def test_missing_family_id_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    del payload["family_id"]
    assert list(validator.iter_errors(payload)), (
        "manifest without family_id must fail validation"
    )


def test_missing_core_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    del payload["core"]
    assert list(validator.iter_errors(payload))


def test_unknown_source_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["required"][0]["source"] = "homebrew"  # not in the closed set
    errors = list(validator.iter_errors(payload))
    assert errors, "unknown source must fail the pattern check"
    assert any("source" in str(err.absolute_path) for err in errors)


def test_vendor_source_without_install_docs_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["recommended"][0]["source"] = "vendor"
    del payload["recommended"][0]["install_docs"]
    errors = list(validator.iter_errors(payload))
    assert errors, "vendor source without install_docs must fail the conditional"


def test_unknown_capability_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["required"][0]["capabilities"] = ["build", "neural-link"]
    errors = list(validator.iter_errors(payload))
    assert errors
    assert any("neural-link" in err.message or "enum" in err.message for err in errors)


def test_uppercase_family_id_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["family_id"] = "STM32F4"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_additional_properties_at_root_fail(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["spurious_field"] = "x"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_additional_properties_in_tool_fail(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["required"][0]["spurious_field"] = "x"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_empty_capabilities_array_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["required"][0]["capabilities"] = []
    errors = list(validator.iter_errors(payload))
    assert errors, "capabilities must declare at least one value (minItems=1)"


def test_duplicate_capability_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["required"][0]["capabilities"] = ["build", "build"]
    errors = list(validator.iter_errors(payload))
    assert errors, "uniqueItems=true should reject duplicates"


def test_bad_github_source_pattern_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["required"][0]["source"] = "github:no-slash-no-repo"
    errors = list(validator.iter_errors(payload))
    assert errors


def test_install_docs_with_no_keys_fails(validator: Draft202012Validator) -> None:
    payload = _valid_manifest()
    payload["recommended"][0]["install_docs"] = {}
    errors = list(validator.iter_errors(payload))
    assert errors, "install_docs must carry at least one of linux/macos/windows"


# ---------------------------------------------------------------------------
# Cross-manifest invariants
# ---------------------------------------------------------------------------


def test_arm_cortex_m_base_carries_the_canonical_required_set() -> None:
    """The ARM base must declare the four tools every Cortex-M project needs.

    Children inherit by `extends:`, so this is the contract the parser
    in task block 2 will rely on when it merges arrays by tool name.
    """
    payload = yaml.safe_load((FAMILIES_DIR / "arm-cortex-m.yml").read_text(encoding="utf-8"))
    required_tools = {entry["tool"] for entry in payload.get("required", [])}
    expected = {"arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"}
    assert expected <= required_tools, (
        f"arm-cortex-m base is missing canonical Cortex-M tools: "
        f"{expected - required_tools}"
    )


def test_arm_extending_families_declare_correct_core() -> None:
    """Cortex-M0+ vs M4F vs M33 — each child must restate its own core."""
    expected_cores = {
        "stm32f4": "cortex-m4f",
        "stm32g0": "cortex-m0plus",
        "rp2040": "cortex-m0plus",
        "nrf52": "cortex-m4f",
    }
    for family_id, expected_core in expected_cores.items():
        payload = yaml.safe_load(
            (FAMILIES_DIR / f"{family_id}.yml").read_text(encoding="utf-8")
        )
        assert payload["extends"] == "arm-cortex-m", (
            f"{family_id} should extend arm-cortex-m"
        )
        assert payload["core"] == expected_core, (
            f"{family_id} should declare core={expected_core!r}, got {payload['core']!r}"
        )


def test_esp32_does_not_extend_arm_base() -> None:
    """Xtensa cannot inherit Cortex-M tooling; the manifest must stand alone."""
    payload = yaml.safe_load((FAMILIES_DIR / "esp32.yml").read_text(encoding="utf-8"))
    assert "extends" not in payload, (
        "esp32 must not extend arm-cortex-m — Xtensa needs its own toolchain"
    )
    required_tools = {entry["tool"] for entry in payload.get("required", [])}
    assert "xtensa-esp-elf-gcc" in required_tools
    assert "esptool" in required_tools
    assert "arm-none-eabi-gcc" not in required_tools


def test_vendor_tools_carry_per_os_install_docs() -> None:
    """Every `source: vendor` tool must link out — we cannot redistribute them.

    Spot-check that at least one vendor tool exists across the seed
    families (otherwise the EULA path is untested) AND that every
    vendor entry declares non-empty install_docs.
    """
    seen_vendor = False
    for path in _all_shipped_paths():
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        for section in ("required", "recommended", "optional"):
            for entry in payload.get(section, []) or []:
                if entry.get("source") != "vendor":
                    continue
                seen_vendor = True
                docs = entry.get("install_docs", {})
                assert docs, (
                    f"{path.name}: vendor tool {entry['tool']!r} has no install_docs"
                )
                # at least one OS link
                assert any(docs.get(os_key) for os_key in ("linux", "macos", "windows")), (
                    f"{path.name}: vendor tool {entry['tool']!r} install_docs has no OS keys"
                )
    assert seen_vendor, (
        "no vendor-source tool in the seed manifests — Wave-1 must exercise "
        "the EULA-gated rendering path"
    )


# ---------------------------------------------------------------------------
# Defensive: copying the baseline must not mutate the source
# ---------------------------------------------------------------------------


def test_valid_manifest_helper_is_isolated() -> None:
    """Two calls return independent dicts so negative tests can mutate freely."""
    a = _valid_manifest()
    b = _valid_manifest()
    a["required"][0]["tool"] = "mutated"
    assert b["required"][0]["tool"] != "mutated"
    # Belt + suspenders: deepcopy round-trip preserves equality.
    assert _valid_manifest() == copy.deepcopy(_valid_manifest())
