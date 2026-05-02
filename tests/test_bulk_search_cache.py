"""Tests for ``add-bulk-search-cache`` (#27)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alloy_cli.core import search as _search
from alloy_cli.core.search import (
    DeviceSummary,
    _bulk_cache_dir,
    _bulk_summaries_from_index,
    _BulkCache,
    _submodule_sha,
)


@pytest.fixture(autouse=True)
def _reset_caches():
    _search.reset_caches()
    yield
    _search.reset_caches()


def _summary(name: str = "stm32g071rb") -> DeviceSummary:
    return DeviceSummary(
        vendor="st",
        family="stm32g0",
        device=name,
        package="lqfp64",
        core="cortex-m0plus",
        summary="STM32G0",
        admitted=False,
        has_features=("uart", "spi"),
    )


def test_bulk_cache_round_trip(tmp_path: Path) -> None:
    cache = _BulkCache(directory=tmp_path / "bulk_search")
    cache.write("abc123", (_summary(),))

    reloaded = cache.read("abc123")
    assert reloaded is not None
    assert reloaded[0].device == "stm32g071rb"
    assert reloaded[0].has_features == ("uart", "spi")


def test_bulk_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = _BulkCache(directory=tmp_path / "bulk_search")
    assert cache.read("zzz") is None


def test_bulk_cache_prunes_to_three_keys(tmp_path: Path) -> None:
    cache = _BulkCache(directory=tmp_path / "bulk_search")
    # Write four SHAs with descending mtimes so the oldest is the
    # one we expect to drop.
    import time

    for sha in ("a", "b", "c", "d"):
        cache.write(sha, (_summary(),))
        time.sleep(0.01)  # ensure distinct mtimes
    keys = sorted(p.stem for p in (tmp_path / "bulk_search").glob("*.json"))
    assert len(keys) == 3
    assert "a" not in keys  # oldest pruned


def test_bulk_cache_unreadable_falls_through(tmp_path: Path) -> None:
    cache_dir = tmp_path / "bulk_search"
    cache_dir.mkdir(parents=True)
    (cache_dir / "abc123.json").write_text("not json", encoding="utf-8")
    cache = _BulkCache(directory=cache_dir)
    assert cache.read("abc123") is None


def test_bulk_cache_invalid_json_schema_returns_none(tmp_path: Path) -> None:
    cache_dir = tmp_path / "bulk_search"
    cache_dir.mkdir(parents=True)
    # Missing the required `vendor` / `family` / `device` fields.
    (cache_dir / "abc123.json").write_text(
        json.dumps([{"vendor": "st"}]), encoding="utf-8"
    )
    cache = _BulkCache(directory=cache_dir)
    assert cache.read("abc123") is None


def test_bulk_summaries_from_index_uses_cache(monkeypatch, tmp_path: Path) -> None:
    """Second invocation hits the cache; the YAML parser does NOT run."""
    fake_dir = tmp_path / "bulk_search"
    monkeypatch.setattr(_search, "_bulk_cache_dir", lambda: fake_dir)
    monkeypatch.setattr(_search, "_submodule_sha", lambda: "deadbeef")

    parser_calls: list[int] = []
    real_loader = _search.yaml.safe_load

    def _counting_loader(stream):
        parser_calls.append(1)
        return real_loader(stream)

    monkeypatch.setattr(_search.yaml, "safe_load", _counting_loader)

    # Plant a synthetic bulk index so the first call has data to
    # parse.  We point alloy-devices-yml's bulk-admitted root at
    # tmp_path so the YAML file lives wherever we want.
    bulk_root = tmp_path / "devices" / "bulk-admitted"
    bulk_root.mkdir(parents=True)
    (bulk_root / "index.yml").write_text(
        "devices:\n"
        "  - vendor: st\n"
        "    family: stm32g0\n"
        "    device: stm32g071rb\n"
        "    package: lqfp64\n"
        "    core: cortex-m0plus\n"
        "    summary: stub\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_search._ir, "data_devices_root", lambda: tmp_path / "devices")

    first = _bulk_summaries_from_index()
    second = _bulk_summaries_from_index()

    assert first == second
    assert len(first) == 1
    # Only the first call should have invoked the YAML parser; the
    # second call comes off the disk cache.
    assert len(parser_calls) == 1


def test_submodule_sha_returns_none_without_git(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(_search._ir, "data_devices_root", lambda: tmp_path / "missing")
    assert _submodule_sha() is None


def test_reset_caches_clears_disk(tmp_path: Path, monkeypatch) -> None:
    fake_dir = tmp_path / "bulk_search"
    monkeypatch.setattr(_search, "_bulk_cache_dir", lambda: fake_dir)

    cache = _BulkCache(directory=fake_dir)
    cache.write("abc", (_summary(),))
    assert (fake_dir / "abc.json").exists()

    _search.reset_caches()
    assert not (fake_dir / "abc.json").exists()


def test_bulk_cache_dir_under_repo_root() -> None:
    """The cache lives next to the lockfile / generated dirs."""
    path = _bulk_cache_dir()
    assert path.name == "bulk_search"
    assert path.parent.name == "cache"
    assert path.parent.parent.name == ".alloy"
