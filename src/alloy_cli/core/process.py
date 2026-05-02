"""Subprocess wrapper that the rest of ``alloy_cli`` uses.

Centralising every external invocation behind ``CommandRunner.run``
gives tests a single seam to mock ``cmake`` / ``probe-rs`` / ``gdb``
without monkey-patching ``subprocess`` itself.

The default :data:`runner` shells out for real; tests inject a
:class:`FakeRunner` (or any callable matching :class:`CommandRunner`).
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of a single subprocess invocation."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def cmdline(self) -> str:
        return " ".join(shlex.quote(a) for a in self.args)


class CommandRunner(Protocol):
    """Anything that can launch a command and return a :class:`CommandResult`."""

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
        capture_output: bool = True,
        timeout: float | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> CommandResult: ...


# ---------------------------------------------------------------------------
# Default real runner
# ---------------------------------------------------------------------------


class _RealRunner:
    """Production :class:`CommandRunner` — calls :func:`subprocess.run`."""

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
        capture_output: bool = True,
        timeout: float | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        argv = tuple(args)
        try:
            if on_line is not None:
                # Stream stdout line-by-line so callers can render progress.
                proc = subprocess.Popen(
                    argv,
                    cwd=str(cwd) if cwd else None,
                    env=dict(env) if env is not None else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                lines: list[str] = []
                assert proc.stdout is not None
                for line in proc.stdout:
                    on_line(line.rstrip("\n"))
                    lines.append(line)
                rc = proc.wait(timeout=timeout)
                return CommandResult(
                    args=argv,
                    returncode=rc,
                    stdout="".join(lines),
                    stderr="",
                )
            completed = subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                env=dict(env) if env is not None else None,
                capture_output=capture_output,
                text=True,
                check=check,
                timeout=timeout,
            )
            return CommandResult(
                args=argv,
                returncode=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
            )
        except FileNotFoundError as exc:
            return CommandResult(
                args=argv,
                returncode=127,
                stdout="",
                stderr=f"command not found: {argv[0]} ({exc})",
            )


runner: CommandRunner = _RealRunner()


# ---------------------------------------------------------------------------
# Fake runner — tests
# ---------------------------------------------------------------------------


@dataclass
class FakeRunner:
    """Test double for :class:`CommandRunner`.

    Configure responses with :meth:`expect`; record actual invocations
    via :attr:`calls`.
    """

    responses: list[tuple[Sequence[str], CommandResult]] = field(default_factory=list)
    calls: list[CommandResult] = field(default_factory=list)
    default: CommandResult | None = None

    def expect(
        self,
        match_args: Sequence[str],
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """Queue a response for the next command whose ``args`` match.

        ``match_args`` is matched as a prefix of the actual command's
        ``args`` tuple — flexible enough to ignore trailing path arguments
        while still pinning the verb chain.
        """
        self.responses.append(
            (
                tuple(match_args),
                CommandResult(
                    args=tuple(match_args),
                    returncode=returncode,
                    stdout=stdout,
                    stderr=stderr,
                ),
            )
        )

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
        capture_output: bool = True,
        timeout: float | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        argv = tuple(args)
        for idx, (match_args, response) in enumerate(self.responses):
            if argv[: len(match_args)] == match_args:
                self.responses.pop(idx)
                actual = CommandResult(
                    args=argv,
                    returncode=response.returncode,
                    stdout=response.stdout,
                    stderr=response.stderr,
                )
                if on_line is not None:
                    for line in response.stdout.splitlines():
                        on_line(line)
                self.calls.append(actual)
                if check and not actual.ok:
                    raise subprocess.CalledProcessError(actual.returncode, list(argv))
                return actual

        if self.default is not None:
            actual = CommandResult(
                args=argv,
                returncode=self.default.returncode,
                stdout=self.default.stdout,
                stderr=self.default.stderr,
            )
            self.calls.append(actual)
            return actual

        raise AssertionError(
            f"FakeRunner: no response queued for {argv!r}.  "
            f"Configure with .expect(...) or set .default."
        )


def configure(new_runner: CommandRunner) -> Callable[[], None]:
    """Swap the module-level runner; returns a function that restores it."""
    global runner
    previous = runner
    runner = new_runner

    def _restore() -> None:
        global runner
        runner = previous

    return _restore


__all__ = [
    "CommandResult",
    "CommandRunner",
    "FakeRunner",
    "configure",
    "runner",
]
