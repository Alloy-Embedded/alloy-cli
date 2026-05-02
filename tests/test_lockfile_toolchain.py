"""Tests for ``core.lockfile_toolchain`` — read / write / round-trip
/ add / remove / diff for ``.alloy/toolchain.lock``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core import lockfile_toolchain as lf
from alloy_cli.core.errors import ProjectConfigError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gcc_pin() -> tuple[str, str, str]:
    return "arm-none-eabi-gcc", "14.2.1-1.1", "a" * 64


def _cmake_pin() -> tuple[str, str, str]:
    return "cmake", "3.31.2", "b" * 64


def _probe_rs_pin() -> tuple[str, str, str]:
    return "probe-rs", "0.27.0", "c" * 64


# ---------------------------------------------------------------------------
# empty / dumps / parse
# ---------------------------------------------------------------------------


def test_empty_lock_dumps_only_schema_version() -> None:
    text = lf.dumps(lf.empty())
    assert text.strip() == 'schema_version = "1.0.0"'


def test_round_trip_through_dumps_and_parse() -> None:
    lock = lf.empty()
    for tool, ver, sha in (_gcc_pin(), _cmake_pin(), _probe_rs_pin()):
        lock = lf.add(lock, tool, ver, sha)
    text = lf.dumps(lock)
    payload = __import__("tomllib").loads(text)
    parsed = lf.parse(payload)
    assert parsed == lock


def test_dumps_is_byte_stable_across_insert_orders() -> None:
    lock_a = lf.empty()
    lock_a = lf.add(lock_a, *_gcc_pin())
    lock_a = lf.add(lock_a, *_cmake_pin())
    lock_a = lf.add(lock_a, *_probe_rs_pin())

    lock_b = lf.empty()
    lock_b = lf.add(lock_b, *_probe_rs_pin())
    lock_b = lf.add(lock_b, *_gcc_pin())
    lock_b = lf.add(lock_b, *_cmake_pin())

    # Different insert order, same byte output (alphabetical key order).
    assert lf.dumps(lock_a) == lf.dumps(lock_b)


def test_dumps_keys_in_alphabetical_order() -> None:
    lock = lf.empty()
    lock = lf.add(lock, *_probe_rs_pin())
    lock = lf.add(lock, *_gcc_pin())
    lock = lf.add(lock, *_cmake_pin())

    text = lf.dumps(lock)
    # Tool keys appear in alphabetical order
    arm_idx = text.index('"arm-none-eabi-gcc"')
    cmake_idx = text.index('"cmake"')
    probe_idx = text.index('"probe-rs"')
    assert arm_idx < cmake_idx < probe_idx


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------


def test_read_missing_file_raises_typed(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError) as exc:
        lf.read(tmp_path / "missing.lock")
    assert "not found" in str(exc.value)


def test_read_optional_returns_none_when_missing(tmp_path: Path) -> None:
    assert lf.read_optional(tmp_path / "missing.lock") is None


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    lock = lf.empty()
    lock = lf.add(lock, *_gcc_pin())
    lock = lf.add(lock, *_probe_rs_pin())
    path = tmp_path / "toolchain.lock"
    lf.write(path, lock)

    assert path.exists()
    re_read = lf.read(path)
    assert re_read == lock


def test_write_creates_parent_directory(tmp_path: Path) -> None:
    lock = lf.add(lf.empty(), *_gcc_pin())
    deep = tmp_path / ".alloy" / "toolchain.lock"
    lf.write(deep, lock)
    assert deep.exists()


def test_read_corrupt_toml_raises_typed(tmp_path: Path) -> None:
    path = tmp_path / "broken.lock"
    path.write_text("schema_version = not.a.string\n[tools]\ngcc = =")
    with pytest.raises(ProjectConfigError) as exc:
        lf.read(path)
    assert "TOML" in str(exc.value) or "parse" in str(exc.value).lower()


def test_read_missing_schema_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "no-version.lock"
    path.write_text("[tools]\n")
    with pytest.raises(ProjectConfigError) as exc:
        lf.read(path)
    assert "schema_version" in str(exc.value)


def test_read_wrong_major_schema_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "wrong-major.lock"
    path.write_text('schema_version = "2.0.0"\n')
    with pytest.raises(ProjectConfigError) as exc:
        lf.read(path)
    assert "major=2" in str(exc.value) or "major" in str(exc.value)


def test_read_invalid_pin_body_raises(tmp_path: Path) -> None:
    """A tool entry missing `version` or `sha256` must error out."""
    path = tmp_path / "bad-pin.lock"
    path.write_text(
        'schema_version = "1.0.0"\n'
        "[tools]\n"
        '"arm-none-eabi-gcc" = { version = "14.2.0" }\n'  # missing sha256
    )
    with pytest.raises(ProjectConfigError) as exc:
        lf.read(path)
    assert "sha256" in str(exc.value)


# ---------------------------------------------------------------------------
# add / remove
# ---------------------------------------------------------------------------


def test_add_to_empty_lock() -> None:
    lock = lf.add(lf.empty(), *_gcc_pin())
    assert "arm-none-eabi-gcc" in lock.tools
    assert lock.tools["arm-none-eabi-gcc"].version == "14.2.1-1.1"


def test_add_overwrites_existing_pin() -> None:
    lock = lf.add(lf.empty(), *_gcc_pin())
    lock = lf.add(lock, "arm-none-eabi-gcc", "14.3.0", "z" * 64)
    assert lock.tools["arm-none-eabi-gcc"].version == "14.3.0"
    assert lock.tools["arm-none-eabi-gcc"].sha256 == "z" * 64


def test_add_returns_new_lock_does_not_mutate() -> None:
    """Wave 1's frozen+slots dataclass pattern — add() returns a new instance."""
    lock_a = lf.empty()
    lock_b = lf.add(lock_a, *_gcc_pin())
    assert lock_a.tools == {}
    assert "arm-none-eabi-gcc" in lock_b.tools


def test_add_rejects_empty_tool_name() -> None:
    with pytest.raises(ProjectConfigError):
        lf.add(lf.empty(), "", "14.2.0", "a" * 64)


def test_add_rejects_empty_version() -> None:
    with pytest.raises(ProjectConfigError):
        lf.add(lf.empty(), "x", "", "a" * 64)


def test_add_rejects_empty_sha() -> None:
    with pytest.raises(ProjectConfigError):
        lf.add(lf.empty(), "x", "1.0", "")


def test_remove_existing_tool() -> None:
    lock = lf.add(lf.empty(), *_gcc_pin())
    lock = lf.add(lock, *_cmake_pin())
    pruned = lf.remove(lock, "cmake")
    assert "cmake" not in pruned.tools
    assert "arm-none-eabi-gcc" in pruned.tools


def test_remove_missing_tool_is_noop() -> None:
    lock = lf.add(lf.empty(), *_gcc_pin())
    pruned = lf.remove(lock, "nonexistent")
    assert pruned == lock


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def test_diff_added() -> None:
    before = lf.empty()
    after = lf.add(before, *_gcc_pin())
    changes = lf.diff(before, after)
    assert len(changes) == 1
    assert changes[0].kind == "added"
    assert changes[0].tool == "arm-none-eabi-gcc"
    assert changes[0].before is None
    assert changes[0].after is not None


def test_diff_removed() -> None:
    before = lf.add(lf.empty(), *_gcc_pin())
    after = lf.empty()
    changes = lf.diff(before, after)
    assert len(changes) == 1
    assert changes[0].kind == "removed"
    assert changes[0].before is not None
    assert changes[0].after is None


def test_diff_version_changed() -> None:
    before = lf.add(lf.empty(), *_gcc_pin())
    after = lf.add(before, "arm-none-eabi-gcc", "14.3.0", "a" * 64)  # same sha
    changes = lf.diff(before, after)
    assert len(changes) == 1
    assert changes[0].kind == "version-changed"


def test_diff_sha_changed() -> None:
    before = lf.add(lf.empty(), *_gcc_pin())
    after = lf.add(before, "arm-none-eabi-gcc", "14.2.1-1.1", "z" * 64)
    changes = lf.diff(before, after)
    assert len(changes) == 1
    assert changes[0].kind == "sha-changed"


def test_diff_multiple_changes_alphabetical() -> None:
    before = lf.empty()
    before = lf.add(before, *_gcc_pin())
    before = lf.add(before, *_cmake_pin())

    after = lf.add(before, "arm-none-eabi-gcc", "14.3.0", "z" * 64)  # changed
    after = lf.remove(after, "cmake")  # removed
    after = lf.add(after, "tio", "2.7", "x" * 64)  # added

    changes = lf.diff(before, after)
    assert [c.tool for c in changes] == ["arm-none-eabi-gcc", "cmake", "tio"]
    assert [c.kind for c in changes] == ["version-changed", "removed", "added"]


def test_diff_no_changes_returns_empty() -> None:
    lock = lf.add(lf.empty(), *_gcc_pin())
    assert lf.diff(lock, lock) == ()


# ---------------------------------------------------------------------------
# Edge: empty tools section is preserved
# ---------------------------------------------------------------------------


def test_empty_tools_table_emits_no_section() -> None:
    """A lock with no tools should emit just `schema_version`, no
    `[tools]` table.  Keeps git diffs clean when a project temporarily
    has no pins.
    """
    text = lf.dumps(lf.empty())
    assert "[tools]" not in text


def test_lockfile_name_constant() -> None:
    assert lf.LOCKFILE_NAME == "toolchain.lock"
