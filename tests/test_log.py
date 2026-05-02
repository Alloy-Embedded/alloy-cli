"""Tests for the structured logger seam (#26)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from alloy_cli.core import log as _log


@pytest.fixture(autouse=True)
def _clean_log_state():
    yield
    _log.reset_for_tests()


def test_get_logger_writes_to_alloy_cli_log(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "alloy-cli.log"
    monkeypatch.setenv("ALLOY_CLI_LOG", str(log_path))

    logger = _log.get_logger("alloy_cli.tests.log")
    logger.error("disk full while writing %s", "events.jsonl")

    body = log_path.read_text(encoding="utf-8")
    assert "disk full while writing events.jsonl" in body
    assert "alloy_cli.tests.log" in body
    assert "ERROR" in body


def test_get_logger_caches_per_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALLOY_CLI_LOG", str(tmp_path / "alloy-cli.log"))

    a = _log.get_logger("alloy_cli.tests.cache")
    b = _log.get_logger("alloy_cli.tests.cache")
    assert a is b
    # Single handler should be installed; calling get_logger twice
    # MUST NOT create a second handler.
    assert len(a.handlers) == 1


def test_reset_for_tests_clears_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALLOY_CLI_LOG", str(tmp_path / "first.log"))
    a = _log.get_logger("alloy_cli.tests.reset")
    monkeypatch.setenv("ALLOY_CLI_LOG", str(tmp_path / "second.log"))
    _log.reset_for_tests()
    b = _log.get_logger("alloy_cli.tests.reset")

    # After reset the next get_logger call rebinds to the new
    # handler; both objects share the same name but the resolved
    # handler is fresh.
    assert b is a
    target_paths = {
        getattr(h, "baseFilename", None) for h in a.handlers if isinstance(h, logging.Handler)
    }
    assert any(
        path is not None and path.endswith("second.log") for path in target_paths
    )


def test_get_logger_falls_back_to_stderr_on_oserror(monkeypatch, tmp_path: Path) -> None:
    """Read-only fs / permission denied → stderr handler, not crash."""
    forbidden = tmp_path / "denied" / "alloy-cli.log"
    monkeypatch.setenv("ALLOY_CLI_LOG", str(forbidden))

    def _explode(*_args, **_kwargs):
        raise OSError("permission denied")

    # Prevent the parent-directory creation from succeeding.
    monkeypatch.setattr(Path, "mkdir", _explode)

    logger = _log.get_logger("alloy_cli.tests.fallback")
    # Should have at least one handler — a StreamHandler fallback.
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
