"""Tests for ``alloy_cli.core.process``: subprocess wrapper + FakeRunner."""

from __future__ import annotations

import pytest

from alloy_cli.core.process import CommandResult, FakeRunner, configure, runner


def test_command_result_ok_and_cmdline() -> None:
    result = CommandResult(args=("ls", "-la", "src"), returncode=0, stdout="", stderr="")
    assert result.ok is True
    assert result.cmdline == "ls -la src"


def test_command_result_quotes_paths_with_spaces() -> None:
    result = CommandResult(
        args=("cmake", "-S", "/some path/with space"), returncode=0, stdout="", stderr=""
    )
    assert "'/some path/with space'" in result.cmdline


def test_fake_runner_returns_queued_response() -> None:
    fake = FakeRunner()
    fake.expect(["cmake", "--version"], stdout="cmake version 3.27.0", returncode=0)
    result = fake.run(["cmake", "--version"])
    assert result.ok
    assert "3.27.0" in result.stdout
    assert fake.calls == [result]


def test_fake_runner_matches_by_prefix() -> None:
    fake = FakeRunner()
    fake.expect(["cmake", "-S"], returncode=0)
    result = fake.run(["cmake", "-S", "/proj", "-B", "/proj/.alloy/build"])
    assert result.ok
    assert result.args[0] == "cmake"


def test_fake_runner_raises_when_no_match() -> None:
    fake = FakeRunner()
    with pytest.raises(AssertionError, match="no response queued"):
        fake.run(["unexpected", "cmd"])


def test_fake_runner_default_response() -> None:
    fake = FakeRunner(default=CommandResult(args=(), returncode=0, stdout="", stderr=""))
    result = fake.run(["something", "unexpected"])
    assert result.ok


def test_fake_runner_streams_lines_to_on_line() -> None:
    fake = FakeRunner()
    fake.expect(["echo"], stdout="alpha\nbeta\ngamma", returncode=0)
    seen: list[str] = []
    fake.run(["echo"], on_line=seen.append)
    assert seen == ["alpha", "beta", "gamma"]


def test_fake_runner_check_raises_on_failure() -> None:
    import subprocess as sp

    fake = FakeRunner()
    fake.expect(["false"], returncode=1)
    with pytest.raises(sp.CalledProcessError):
        fake.run(["false"], check=True)


def test_configure_swaps_module_runner_and_restores() -> None:
    original = runner
    fake = FakeRunner()
    restore = configure(fake)
    try:
        from alloy_cli.core import process

        assert process.runner is fake
    finally:
        restore()
    from alloy_cli.core import process as p2

    assert p2.runner is original
