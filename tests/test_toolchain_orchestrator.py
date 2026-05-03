"""Tests for ``core.toolchain_orchestrator`` — the shared install
walker every Wave-3 entry point routes through.

Spec scenarios pinned here (from
``openspec/changes/add-onboarding-wizard/specs/toolchain-onboarding/spec.md``):

  * ``install_family`` walks every non-vendor tool through the
    manager.
  * Vendor tools never reach the downloader.
  * Lockfile write is gated by ``project_root``.
  * A tool failure does not abort the rest of the walk.
  * Idempotent re-run produces ``skipped-already-installed`` outcomes.
  * Events fire in order per tool (started → downloaded → installed).
  * ``--shared`` semantics (``project_root=None``) skip the lockfile.
"""

from __future__ import annotations

import hashlib
import tarfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from alloy_cli.core import lockfile_toolchain as _lf
from alloy_cli.core import tool_sources as _ts
from alloy_cli.core import toolchain_orchestrator as _orch
from alloy_cli.core.errors import OnboardingCancelledError
from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact
from alloy_cli.core.toolchain_orchestrator import (
    InstallEvent,
    InstallOutcome,
    ToolInstalled,
    ToolSkippedVendor,
    ToolStarted,
    install_family,
)
from alloy_cli.core.toolchain_registry import (
    FamilyManifest,
    ToolRequirement,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(root / "tools"))
    return root


def _sha_of(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _make_fixture_tar(
    tmp_path: Path,
    *,
    name: str,
    extract_to_subdir: str,
    binaries: Sequence[str],
) -> Path:
    src = tmp_path / "_pkg" / name / extract_to_subdir
    for binary in binaries:
        target = src / binary
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\nfake\n", encoding="utf-8")
    archive = tmp_path / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname=extract_to_subdir)
    return archive


def _build_artifact(
    *,
    tool: str,
    version: str,
    source: str,
    archive: Path,
    extract_to_subdir: str,
    binaries: tuple[str, ...],
) -> SourceArtifact:
    return SourceArtifact(
        tool=tool,
        version=version,
        source=source,
        url=f"https://example.com/{tool}-{version}.tar.gz",
        sha256=_sha_of(archive.read_bytes()),
        archive_kind="tar.gz",
        extract_to_subdir=extract_to_subdir,
        binaries=binaries,
    )


def _stub_pinned_artifact(
    monkeypatch: pytest.MonkeyPatch,
    artifact: SourceArtifact,
) -> None:
    """Patch ``adapter_for(...)`` so ``resolve(...)`` returns ``artifact``.

    The orchestrator calls ``adapter_for(tool.source).resolve(...)``;
    we substitute the resolver so tests don't need a real pin file
    or schema-shaped fixture.
    """
    real_adapter_for = _ts.adapter_for

    class _StubAdapter:
        kind = "test-stub"

        def resolve(self, tool, host):  # type: ignore[no-untyped-def]
            if tool.tool == artifact.tool:
                return artifact
            real = real_adapter_for(tool.source)
            return real.resolve(tool, host)

    def _patched(source: str):  # type: ignore[no-untyped-def]
        if source == artifact.source or source.startswith("xpack"):
            return _StubAdapter()
        return real_adapter_for(source)

    monkeypatch.setattr(_ts, "adapter_for", _patched)


def _arm_gcc_req(*, version: str = "1.0") -> ToolRequirement:
    return ToolRequirement(
        tool="arm-none-eabi-gcc",
        version=version,
        source="xpack",
        capabilities=("build", "debug"),
        bundles=("arm-none-eabi-gdb",),
    )


def _vendor_req() -> ToolRequirement:
    return ToolRequirement(
        tool="STM32CubeProgrammer",
        version=">=2.16",
        source="vendor",
        capabilities=("flash", "recovery"),
        install_docs={"macos": "https://www.st.com/macos.html"},
    )


def _make_manifest(
    *,
    family_id: str = "test-family",
    required: tuple[ToolRequirement, ...] = (),
    recommended: tuple[ToolRequirement, ...] = (),
    optional: tuple[ToolRequirement, ...] = (),
) -> FamilyManifest:
    return FamilyManifest(
        family_id=family_id,
        core="cortex-m4f",
        arch="armv7em",
        schema_version="1.0.0",
        required=required,
        recommended=recommended,
        optional=optional,
    )


def _install_one_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tool: str = "arm-none-eabi-gcc",
    version: str = "1.0",
) -> tuple[FamilyManifest, FakeDownloader, SourceArtifact]:
    """Set up a manifest with one required tool + fixture artefact."""
    archive = _make_fixture_tar(
        tmp_path,
        name=f"{tool}-{version}",
        extract_to_subdir=f"{tool}-{version}",
        binaries=(f"bin/{tool}", "bin/arm-none-eabi-gdb"),
    )
    artifact = _build_artifact(
        tool=tool,
        version=version,
        source="xpack",
        archive=archive,
        extract_to_subdir=f"{tool}-{version}",
        binaries=(f"bin/{tool}", "bin/arm-none-eabi-gdb"),
    )
    _stub_pinned_artifact(monkeypatch, artifact)

    fake_dl = FakeDownloader()
    fake_dl.expect(artifact.url, archive)

    manifest = _make_manifest(
        required=(
            ToolRequirement(
                tool=tool,
                version=version,
                source="xpack",
                capabilities=("build",),
                bundles=("arm-none-eabi-gdb",),
            ),
        ),
    )
    return manifest, fake_dl, artifact


# ---------------------------------------------------------------------------
# Happy path: every required tool installs
# ---------------------------------------------------------------------------


def test_install_family_walks_required_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, fake_dl, artifact = _install_one_tool(tmp_path, monkeypatch)

    project = tmp_path / "proj"
    project.mkdir()
    events: list[InstallEvent] = []

    report = install_family(
        manifest,
        project_root=project,
        downloader=fake_dl,
        on_event=events.append,
    )

    assert report.family_id == "test-family"
    assert report.installed_count == 1
    assert report.failed_count == 0
    assert report.lockfile_updated is True
    # Lockfile pins the tool
    lock_path = project / ".alloy" / _lf.LOCKFILE_NAME
    assert lock_path.exists()
    lock = _lf.read(lock_path)
    assert "arm-none-eabi-gcc" in lock.tools
    assert lock.tools["arm-none-eabi-gcc"].sha256 == artifact.sha256


def test_install_family_emits_started_then_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, fake_dl, _ = _install_one_tool(tmp_path, monkeypatch)
    events: list[InstallEvent] = []

    install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=fake_dl,
        on_event=events.append,
    )

    # Find the events for our tool in order
    tool_events = [
        type(e).__name__ for e in events if getattr(e, "tool", None) == "arm-none-eabi-gcc"
    ]
    assert tool_events[0] == "ToolStarted"
    # ToolDownloaded fires when bytes_downloaded > 0
    assert "ToolDownloaded" in tool_events
    assert tool_events[-1] == "ToolInstalled"


def test_install_family_returns_typed_report_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, fake_dl, _ = _install_one_tool(tmp_path, monkeypatch)

    report = install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=fake_dl,
    )
    assert len(report.outcomes) == 1
    outcome = report.outcomes[0]
    assert isinstance(outcome, InstallOutcome)
    assert outcome.tool == "arm-none-eabi-gcc"
    assert outcome.state == "installed"
    assert outcome.installed is True
    assert outcome.skipped is False
    assert outcome.bytes_downloaded > 0


# ---------------------------------------------------------------------------
# Vendor short-circuit
# ---------------------------------------------------------------------------


def test_vendor_tool_emits_skipped_event_no_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _make_manifest(recommended=(_vendor_req(),))
    events: list[InstallEvent] = []

    # Use an exploding downloader to verify the orchestrator never invokes it.
    class _ExplodingDL:
        def fetch(self, *_args, **_kwargs):
            raise AssertionError("downloader should not be invoked for vendor")

    report = install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=_ExplodingDL(),  # type: ignore[arg-type]
        on_event=events.append,
    )

    # One outcome, vendor-skipped
    assert len(report.outcomes) == 1
    assert report.outcomes[0].state == "skipped-vendor"
    assert report.outcomes[0].install_doc_url == "https://www.st.com/macos.html"

    # Single ToolSkippedVendor event
    skipped = [e for e in events if isinstance(e, ToolSkippedVendor)]
    assert len(skipped) == 1
    assert skipped[0].install_doc_url == "https://www.st.com/macos.html"


def test_vendor_tool_does_not_appear_in_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _make_manifest(recommended=(_vendor_req(),))

    project = tmp_path / "proj"
    project.mkdir()
    install_family(manifest, project_root=project)

    # No lockfile written (only vendor tool, nothing installed)
    lock_path = project / ".alloy" / _lf.LOCKFILE_NAME
    assert not lock_path.exists()


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


def test_one_tool_failure_does_not_abort_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checksum mismatch on tool 1 must not stop tool 2 from installing."""
    archive_a = _make_fixture_tar(
        tmp_path,
        name="a-1.0",
        extract_to_subdir="a-1.0",
        binaries=("bin/a",),
    )
    archive_b = _make_fixture_tar(
        tmp_path,
        name="b-1.0",
        extract_to_subdir="b-1.0",
        binaries=("bin/b",),
    )
    art_a = _build_artifact(
        tool="tool-a",
        version="1.0",
        source="xpack",
        archive=archive_a,
        extract_to_subdir="a-1.0",
        binaries=("bin/a",),
    )
    # Pre-corrupt: the artefact SHA pins zeros, the fixture has real bytes
    art_a_corrupt = replace(art_a, sha256="0" * 64)
    art_b = _build_artifact(
        tool="tool-b",
        version="1.0",
        source="xpack",
        archive=archive_b,
        extract_to_subdir="b-1.0",
        binaries=("bin/b",),
    )

    real_adapter_for = _ts.adapter_for

    class _StubAdapter:
        kind = "stub"

        def resolve(self, tool, host):  # type: ignore[no-untyped-def]
            if tool.tool == "tool-a":
                return art_a_corrupt
            if tool.tool == "tool-b":
                return art_b
            return real_adapter_for(tool.source).resolve(tool, host)

    monkeypatch.setattr(_ts, "adapter_for", lambda _s: _StubAdapter())

    fake_dl = FakeDownloader()
    fake_dl.expect(art_a_corrupt.url, archive_a)
    fake_dl.expect(art_b.url, archive_b)

    manifest = _make_manifest(
        required=(
            ToolRequirement(tool="tool-a", version="1.0", source="xpack", capabilities=("build",)),
            ToolRequirement(tool="tool-b", version="1.0", source="xpack", capabilities=("build",)),
        ),
    )

    events: list[InstallEvent] = []
    report = install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=fake_dl,
        on_event=events.append,
    )

    # Both tools visited; one failed, one installed
    assert len(report.outcomes) == 2
    by_tool = {o.tool: o for o in report.outcomes}
    assert by_tool["tool-a"].state == "failed"
    assert by_tool["tool-a"].error_type == "family-toolchain-installer-checksum"
    assert by_tool["tool-b"].state == "installed"

    # Lockfile contains tool-b only
    lock = _lf.read(tmp_path / "proj" / ".alloy" / _lf.LOCKFILE_NAME)
    assert "tool-a" not in lock.tools
    assert "tool-b" in lock.tools


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_re_run_produces_skipped_already_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, fake_dl, _ = _install_one_tool(tmp_path, monkeypatch)

    project = tmp_path / "proj"
    project.mkdir()

    # First run installs
    first = install_family(manifest, project_root=project, downloader=fake_dl)
    assert first.outcomes[0].state == "installed"
    assert first.outcomes[0].bytes_downloaded > 0

    # Second run is a no-op
    second = install_family(manifest, project_root=project, downloader=fake_dl)
    assert second.outcomes[0].state == "skipped-already-installed"
    assert second.outcomes[0].bytes_downloaded == 0
    assert second.outcomes[0].installed is True
    assert second.outcomes[0].skipped is True
    assert second.total_bytes_downloaded == 0


# ---------------------------------------------------------------------------
# --shared semantics (no lockfile write)
# ---------------------------------------------------------------------------


def test_install_family_skips_lockfile_when_project_root_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, fake_dl, _ = _install_one_tool(tmp_path, monkeypatch)

    report = install_family(manifest, project_root=None, downloader=fake_dl)
    assert report.installed_count == 1
    assert report.lockfile_updated is False
    assert report.lockfile_path is None
    # No project lockfile anywhere under tmp_path
    assert not list(tmp_path.rglob("toolchain.lock"))


# ---------------------------------------------------------------------------
# include_optional gate
# ---------------------------------------------------------------------------


def test_optional_tier_skipped_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _make_fixture_tar(
        tmp_path,
        name="opt-1.0",
        extract_to_subdir="opt-1.0",
        binaries=("bin/opt",),
    )
    art = _build_artifact(
        tool="opt-tool",
        version="1.0",
        source="xpack",
        archive=archive,
        extract_to_subdir="opt-1.0",
        binaries=("bin/opt",),
    )
    _stub_pinned_artifact(monkeypatch, art)
    fake_dl = FakeDownloader()
    fake_dl.expect(art.url, archive)

    manifest = _make_manifest(
        optional=(
            ToolRequirement(
                tool="opt-tool", version="1.0", source="xpack", capabilities=("build",)
            ),
        ),
    )

    # Default: optional skipped → empty outcomes
    report = install_family(manifest, project_root=tmp_path / "proj", downloader=fake_dl)
    assert report.outcomes == ()

    # include_optional=True → walks the tier
    report2 = install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=fake_dl,
        include_optional=True,
    )
    assert report2.installed_count == 1


# ---------------------------------------------------------------------------
# UI-free contract: orchestrator must not import sys.stdin / Console / etc.
# ---------------------------------------------------------------------------


def test_orchestrator_module_is_ui_free() -> None:
    """The orchestrator must NEVER import Click, Rich, Textual, or
    reference ``sys.stdin`` / call bare ``input(...)``.  Walks the
    AST to avoid false positives in docstrings.
    """
    import ast
    import inspect

    source = inspect.getsource(_orch)
    tree = ast.parse(source)

    forbidden_imports = {"click", "rich", "textual"}

    def _module_root(name: str) -> str:
        return name.split(".", 1)[0]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _module_root(alias.name)
                assert root not in forbidden_imports, f"orchestrator must not `import {alias.name}`"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = _module_root(node.module)
            assert root not in forbidden_imports, (
                f"orchestrator must not `from {node.module} import ...`"
            )
        elif isinstance(node, ast.Call):
            func = node.func
            # Bare ``input(...)`` call
            if isinstance(func, ast.Name) and func.id == "input":
                raise AssertionError(
                    "orchestrator must not call bare `input(...)` — "
                    "interactive prompts live in commands/, not core/"
                )
            # ``sys.stdin.something`` access
            if isinstance(func, ast.Attribute):
                # Walk attribute chain to find sys.stdin
                cursor: ast.expr | None = func
                while isinstance(cursor, ast.Attribute):
                    cursor = cursor.value
                if isinstance(cursor, ast.Name) and cursor.id == "sys":
                    # Check the chain mentions stdin
                    chain: list[str] = []
                    walker: ast.expr = func
                    while isinstance(walker, ast.Attribute):
                        chain.append(walker.attr)
                        walker = walker.value
                    if "stdin" in chain:
                        raise AssertionError("orchestrator must not reference sys.stdin")


# ---------------------------------------------------------------------------
# Event ordering
# ---------------------------------------------------------------------------


def test_event_callback_fires_in_order_per_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, fake_dl, _ = _install_one_tool(tmp_path, monkeypatch)
    events: list[InstallEvent] = []

    install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=fake_dl,
        on_event=events.append,
    )

    # Within events for the same tool, ToolStarted strictly precedes
    # ToolInstalled (ToolDownloaded falls between when bytes > 0).
    started_idx = next(i for i, e in enumerate(events) if isinstance(e, ToolStarted))
    installed_idx = next(i for i, e in enumerate(events) if isinstance(e, ToolInstalled))
    assert started_idx < installed_idx


def test_no_callback_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``on_event=None`` is a valid no-op argument."""
    manifest, fake_dl, _ = _install_one_tool(tmp_path, monkeypatch)
    install_family(
        manifest,
        project_root=tmp_path / "proj",
        downloader=fake_dl,
        on_event=None,
    )


# ---------------------------------------------------------------------------
# Outcome.installed / .skipped semantics
# ---------------------------------------------------------------------------


def test_outcome_installed_property() -> None:
    o_installed = InstallOutcome(tool="x", version="1", state="installed")
    o_already = InstallOutcome(tool="x", version="1", state="skipped-already-installed")
    o_vendor = InstallOutcome(tool="x", version="1", state="skipped-vendor")
    o_failed = InstallOutcome(tool="x", version="1", state="failed")

    assert o_installed.installed is True
    assert o_already.installed is True  # in the store, ready to use
    assert o_vendor.installed is False
    assert o_failed.installed is False


def test_outcome_skipped_property() -> None:
    o_installed = InstallOutcome(tool="x", version="1", state="installed")
    o_already = InstallOutcome(tool="x", version="1", state="skipped-already-installed")
    o_vendor = InstallOutcome(tool="x", version="1", state="skipped-vendor")
    o_host = InstallOutcome(tool="x", version="1", state="skipped-host-unsupported")
    o_failed = InstallOutcome(tool="x", version="1", state="failed")

    assert o_installed.skipped is False
    assert o_already.skipped is True
    assert o_vendor.skipped is True
    assert o_host.skipped is True
    assert o_failed.skipped is False  # failed != skipped


# ---------------------------------------------------------------------------
# OnboardingCancelledError attaches partial outcomes
# ---------------------------------------------------------------------------


def test_onboarding_cancelled_carries_partial_outcomes() -> None:
    a = InstallOutcome(tool="a", version="1", state="installed")
    b = InstallOutcome(tool="b", version="1", state="failed")
    err = OnboardingCancelledError(partial_outcomes=(a, b))
    assert err.partial_outcomes == (a, b)
    assert err.error_type == "onboarding-cancelled"
