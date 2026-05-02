"""Structured logger for alloy-cli.

Every module that previously held a bare ``except Exception`` now
funnels its suppressed errors through here so a maintainer can
grep ``.alloy/cache/alloy-cli.log`` after the fact instead of
guessing why something silently failed.

The log path defaults to ``.alloy/cache/alloy-cli.log`` under
the project root, but the ``ALLOY_CLI_LOG`` environment variable
overrides that — useful when tests need a tmp-scoped path.

Rotation: a single ``.1`` backup once the file passes 1 MB.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_DEFAULT_FILENAME = "alloy-cli.log"
_MAX_BYTES = 1_048_576  # 1 MB — matches the spec
_BACKUP_COUNT = 1

# Module-level cache so we configure each logger once per process.
_CONFIGURED: set[str] = set()


def _resolve_log_path() -> Path:
    """Return the active log file path.

    ``ALLOY_CLI_LOG`` wins over the default; otherwise we land
    inside the cwd's ``.alloy/cache/`` directory.  We deliberately
    don't auto-create the parent here — production callers go
    through :class:`AlloyDir.ensure`, and tests pin the override.
    """
    env_override = os.environ.get("ALLOY_CLI_LOG")
    if env_override:
        return Path(env_override)
    return Path.cwd() / ".alloy" / "cache" / _DEFAULT_FILENAME


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to ``.alloy/cache/alloy-cli.log``.

    Each unique ``name`` is configured once per process; subsequent
    calls are cheap and reuse the existing handler.  Failures to
    write to the log file fall back to a stderr handler so the
    logger always has somewhere to go.
    """
    logger = logging.getLogger(name)
    if name in _CONFIGURED:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    path = _resolve_log_path()
    handler: logging.Handler
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        # Read-only fs / permission denied — still want a working
        # logger, even if it ends up shouting into stderr.
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
    )
    logger.addHandler(handler)
    _CONFIGURED.add(name)
    return logger


def reset_for_tests() -> None:
    """Clear the per-process configuration cache.

    Test fixtures pin ``ALLOY_CLI_LOG`` per-test; calling this in
    a fixture teardown ensures the next test re-binds the handler
    to the new path instead of the previous one.
    """
    for name in list(_CONFIGURED):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
    _CONFIGURED.clear()


__all__ = ["get_logger", "reset_for_tests"]
