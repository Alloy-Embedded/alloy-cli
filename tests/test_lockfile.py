"""Round-trip tests for the lockfile reader/writer."""

from __future__ import annotations

import pytest

from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.lockfile import LOCKFILE_SCHEMA_VERSION, AlloyLockfile, read_lock, write_lock


def test_roundtrip_preserves_pinned_versions(tmp_path) -> None:
    lock_path = tmp_path / "version.lock"
    original = AlloyLockfile(
        schema_version=LOCKFILE_SCHEMA_VERSION,
        alloy="0.7.3",
        alloy_codegen="0.4.1",
        alloy_devices_yml="1.5.0",
        alloy_cli="0.5.0",
    )
    write_lock(lock_path, original)
    decoded = read_lock(lock_path)
    assert decoded == original


def test_partial_pins_round_trip(tmp_path) -> None:
    lock_path = tmp_path / "version.lock"
    original = AlloyLockfile(
        schema_version="1.0.0",
        alloy="0.7.3",
        alloy_codegen=None,
        alloy_devices_yml=None,
        alloy_cli=None,
    )
    write_lock(lock_path, original)
    decoded = read_lock(lock_path)
    assert decoded.alloy == "0.7.3"
    assert decoded.alloy_codegen is None


def test_missing_lockfile_raises(tmp_path) -> None:
    with pytest.raises(AlloyCliError):
        read_lock(tmp_path / "does_not_exist.lock")
