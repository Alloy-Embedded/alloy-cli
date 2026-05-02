"""Tests for ``core.toolchain_manager`` — content-addressed store,
atomic install, idempotent re-runs, concurrency lock, prune semantics,
udev rules emission.

Every test redirects ``ALLOY_TOOLS_ROOT`` to ``tmp_path`` so the
real user-data directory is never touched.  Fixture tarballs are
built on the fly with deterministic content so SHA matches travel
through the FakeDownloader path honestly.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from alloy_cli.core import lockfile_toolchain as lf
from alloy_cli.core import toolchain_manager as tm
from alloy_cli.core.errors import (
    FamilyToolchainInstallerExtractError,
    FamilyToolchainInstallerLockedError,
    FamilyToolchainInstallerStoreCorruptError,
)
from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_store_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every test's ``store_root()`` to a fresh tmp dir."""
    root = tmp_path / "alloy-tools"
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(root / "tools"))
    return root


def _sha_of(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _make_tarball(
    tmp_path: Path,
    *,
    name: str = "fake-tool.tar.gz",
    subdir: str = "fake-tool-1.0",
    binary_rel: str = "bin/fake-gcc",
    binary_body: bytes = b"#!/bin/sh\necho fake\n",
) -> Path:
    src_root = tmp_path / "_src" / subdir
    bin_dir = src_root / Path(binary_rel).parent
    bin_dir.mkdir(parents=True, exist_ok=True)
    (src_root / binary_rel).write_bytes(binary_body)
    archive = tmp_path / name
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src_root, arcname=subdir)
    return archive


def _make_zipball(
    tmp_path: Path,
    *,
    name: str = "fake.zip",
    binary_rel: str = "bin/fake-gcc.exe",
    binary_body: bytes = b"MZ\x00\x00",
) -> Path:
    src_root = tmp_path / "_src"
    target = src_root / binary_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(binary_body)
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(target, arcname=binary_rel)
    return archive


def _artefact_for(
    archive: Path,
    *,
    tool: str = "fake-gcc",
    version: str = "1.0.0",
    archive_kind: str = "tar.gz",
    extract_to_subdir: str = "fake-tool-1.0",
    binaries: tuple[str, ...] = ("bin/fake-gcc",),
    udev_rules: str = "",
) -> SourceArtifact:
    return SourceArtifact(
        tool=tool,
        version=version,
        source="xpack",
        url=f"https://example.com/{archive.name}",
        sha256=_sha_of(archive.read_bytes()),
        archive_kind=archive_kind,
        extract_to_subdir=extract_to_subdir,
        binaries=binaries,
        udev_rules=udev_rules,
    )


def _fake_dl(*, archive: Path, url: str | None = None) -> FakeDownloader:
    fake = FakeDownloader()
    fake.expect(url or f"https://example.com/{archive.name}", archive)
    return fake


# ---------------------------------------------------------------------------
# Install — happy path
# ---------------------------------------------------------------------------


def test_install_atomic_creates_store_and_manifest(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)

    outcome = tm.install(artifact, downloader=_fake_dl(archive=archive))

    assert outcome.skipped is False
    assert outcome.bytes_downloaded > 0
    # Store path exists and contains the flattened binary
    assert outcome.store_path.is_dir()
    assert (outcome.store_path / "bin/fake-gcc").exists()
    # Manifest entry recorded
    installed = tm.list_installed()
    assert len(installed) == 1
    assert installed[0].tool == "fake-gcc"
    assert installed[0].version == "1.0.0"
    assert installed[0].sha256 == artifact.sha256


def test_install_promotes_via_os_rename(tmp_path: Path) -> None:
    """No partial / temp file remains under store/.tmp/ after success."""
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)

    tm.install(artifact, downloader=_fake_dl(archive=archive))

    tmp_subdir = tm.store_root() / "store" / ".tmp"
    assert tmp_subdir.exists()
    leftovers = list(tmp_subdir.iterdir())
    assert leftovers == [], f"unexpected tmp leftovers: {leftovers}"


def test_install_creates_by_name_link(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)

    tm.install(artifact, downloader=_fake_dl(archive=archive))

    by_name = tm.store_root() / "by-name" / "fake-gcc" / "1.0.0"
    # On POSIX it's a symlink; on Windows fallback it's a dir with _pointer.txt
    assert by_name.exists() or (by_name / "_pointer.txt").exists()
    if by_name.is_symlink():
        target = by_name.resolve()
        assert target == _store_dir_for(artifact)


def _store_dir_for(artifact: SourceArtifact) -> Path:
    return tm.store_root() / "store" / artifact.sha256


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_re_install_is_noop(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    fake = _fake_dl(archive=archive)

    first = tm.install(artifact, downloader=fake)
    assert first.skipped is False
    assert len(fake.calls) == 1

    second = tm.install(artifact, downloader=fake)
    assert second.skipped is True
    # No additional download
    assert len(fake.calls) == 1


def test_force_reinstall_skips_idempotency(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    fake = _fake_dl(archive=archive)

    tm.install(artifact, downloader=fake)
    forced = tm.install(artifact, downloader=fake, force=True)
    assert forced.skipped is False
    assert len(fake.calls) == 2  # second call really hit the (fake) network


# ---------------------------------------------------------------------------
# Checksum / extract failure paths
# ---------------------------------------------------------------------------


def test_checksum_mismatch_leaves_store_untouched(tmp_path: Path) -> None:
    """A pre-corrupted artefact must NOT promote to store/<sha>/."""
    from alloy_cli.core.errors import FamilyToolchainInstallerChecksumError

    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    bad_artifact = SourceArtifact(
        tool=artifact.tool,
        version=artifact.version,
        source=artifact.source,
        url=artifact.url,
        sha256="0" * 64,  # placeholder that won't match
        archive_kind=artifact.archive_kind,
        extract_to_subdir=artifact.extract_to_subdir,
        binaries=artifact.binaries,
    )

    with pytest.raises(FamilyToolchainInstallerChecksumError):
        tm.install(bad_artifact, downloader=_fake_dl(archive=archive))

    # Nothing landed under store/<bad_sha>/
    bad_store = tm.store_root() / "store" / ("0" * 64)
    assert not bad_store.exists()
    # Manifest is empty
    assert tm.list_installed() == []


def test_path_traversal_in_archive_rejected(tmp_path: Path) -> None:
    """A tarball whose member tries to escape the extract dir must
    surface the typed extract error."""
    src_root = tmp_path / "_evil"
    src_root.mkdir()
    (src_root / "ok.txt").write_bytes(b"hi")
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        # Manually construct a member with a traversal name
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = 4
        from io import BytesIO

        tar.addfile(info, BytesIO(b"BAD!"))

    artifact = _artefact_for(
        archive,
        extract_to_subdir="",
    )
    with pytest.raises(FamilyToolchainInstallerExtractError):
        tm.install(artifact, downloader=_fake_dl(archive=archive))


def test_unknown_archive_kind_raises(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = SourceArtifact(
        tool="fake",
        version="1.0",
        source="xpack",
        url=f"https://example.com/{archive.name}",
        sha256=_sha_of(archive.read_bytes()),
        archive_kind="rar",  # not in the closed enum
        extract_to_subdir="",
        binaries=("bin/fake",),
    )
    with pytest.raises(FamilyToolchainInstallerExtractError):
        tm.install(artifact, downloader=_fake_dl(archive=archive))


# ---------------------------------------------------------------------------
# Concurrency lock
# ---------------------------------------------------------------------------


def test_concurrent_install_raises_locked() -> None:
    """A second install while the first holds the flock raises typed."""
    tm.ensure_store()
    # Hold the lock manually; nested context would also work.
    cm = tm._store_lock()
    cm.__enter__()
    try:
        with pytest.raises(FamilyToolchainInstallerLockedError):
            with tm._store_lock():
                pass
    finally:
        cm.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# resolve / verify / store-corrupt
# ---------------------------------------------------------------------------


def test_resolve_returns_absolute_path_to_primary_binary(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    resolved = tm.resolve("fake-gcc")
    assert resolved is not None
    assert resolved.is_absolute()
    assert resolved.exists()
    assert resolved.name == "fake-gcc"


def test_resolve_by_bundled_name_finds_via_binaries(tmp_path: Path) -> None:
    """Pass a bundle entry's basename and we should walk binaries[]."""
    # Build a tarball that contains BOTH gcc and gdb so the bundle
    # resolution path has real files to point at.
    _make_tarball(tmp_path, binary_rel="bin/fake-gdb")  # creates the layout
    src = tmp_path / "_src" / "fake-tool-1.0" / "bin"
    (src / "fake-gcc").write_bytes(b"#!/bin/sh\nfake\n")
    archive_v2 = tmp_path / "fake-bundle.tar.gz"
    with tarfile.open(archive_v2, "w:gz") as tar:
        tar.add(tmp_path / "_src" / "fake-tool-1.0", arcname="fake-tool-1.0")
    artifact_v2 = SourceArtifact(
        tool="fake-gcc",
        version="1.0.0",
        source="xpack",
        url=f"https://example.com/{archive_v2.name}",
        sha256=_sha_of(archive_v2.read_bytes()),
        archive_kind="tar.gz",
        extract_to_subdir="fake-tool-1.0",
        binaries=("bin/fake-gcc", "bin/fake-gdb"),
    )
    tm.install(artifact_v2, downloader=_fake_dl(archive=archive_v2))

    # Lookup by bundle name resolves to that bundle's path
    gdb = tm.resolve("fake-gdb")
    assert gdb is not None
    assert gdb.name == "fake-gdb"
    assert gdb.exists()


def test_resolve_returns_none_for_unknown_tool(tmp_path: Path) -> None:
    assert tm.resolve("never-installed") is None


def test_resolve_raises_when_store_dir_missing(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    # User does `rm -rf store/<sha>` by hand
    import shutil as _shutil

    _shutil.rmtree(tm.store_root() / "store" / artifact.sha256)

    with pytest.raises(FamilyToolchainInstallerStoreCorruptError):
        tm.resolve("fake-gcc")


def test_verify_returns_true_when_binaries_present(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))
    assert tm.verify("fake-gcc") is True


def test_verify_returns_false_when_binary_missing(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    # Delete just the binary inside the store
    bin_path = artifact_store_path(artifact) / "bin" / "fake-gcc"
    bin_path.unlink()
    assert tm.verify("fake-gcc") is False


def artifact_store_path(artifact: SourceArtifact) -> Path:
    return tm.store_root() / "store" / artifact.sha256


def test_verify_returns_false_when_unknown(tmp_path: Path) -> None:
    assert tm.verify("never-installed") is False


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


def test_prune_dry_run_lists_unreferenced_versions(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    # No projects pinning anything → every entry is a candidate
    report = tm.prune(projects=(), dry_run=True)
    assert report.dry_run is True
    assert len(report.candidates) == 1
    assert report.candidates[0].tool == "fake-gcc"
    assert report.deleted == ()
    # Store dir is still there
    assert artifact_store_path(artifact).is_dir()


def test_prune_deletes_unreferenced(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    report = tm.prune(projects=(), dry_run=False)
    assert len(report.deleted) == 1
    assert report.bytes_freed > 0
    # Store dir is gone, manifest is empty
    assert not artifact_store_path(artifact).is_dir()
    assert tm.list_installed() == []


def test_prune_keeps_referenced_versions(tmp_path: Path) -> None:
    """A project pinning the (tool, version, sha) triple must NOT be pruned."""
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    # Build a project with a lockfile pinning this exact triple
    project_root = tmp_path / "myproj"
    project_root.mkdir()
    lock_path = project_root / ".alloy" / lf.LOCKFILE_NAME
    lock = lf.add(lf.empty(), "fake-gcc", "1.0.0", artifact.sha256)
    lf.write(lock_path, lock)

    report = tm.prune(projects=(project_root,), dry_run=False)
    assert report.deleted == ()
    assert artifact_store_path(artifact).is_dir()
    assert tm.list_installed()


def test_prune_dry_run_does_not_modify_manifest(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    before = tm.list_installed()
    tm.prune(projects=(), dry_run=True)
    after = tm.list_installed()
    assert before == after


# ---------------------------------------------------------------------------
# udev rules
# ---------------------------------------------------------------------------


def test_udev_rules_emitted_on_linux_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the artefact carries udev_rules AND the host is Linux,
    a `<store>/udev/<tool>.rules` file is written.  On macOS / Windows
    the rules block is silently ignored.
    """
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(
        archive,
        udev_rules="SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"1234\", MODE=\"0666\"\n",
    )

    captured: list[str] = []
    monkeypatch.setattr(tm.platform, "system", lambda: "Linux")
    outcome = tm.install(
        artifact,
        downloader=_fake_dl(archive=archive),
        on_line=captured.append,
    )

    assert outcome.udev_rules_path is not None
    assert outcome.udev_rules_path.exists()
    assert outcome.udev_rules_path.read_text(encoding="utf-8").startswith(
        "SUBSYSTEMS"
    )
    # Sudo instruction was emitted but never executed
    joined = "\n".join(captured)
    assert "sudo cp" in joined
    assert "udevadm control --reload-rules" in joined


def test_udev_rules_silent_on_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive, udev_rules="some rules")
    monkeypatch.setattr(tm.platform, "system", lambda: "Darwin")

    outcome = tm.install(artifact, downloader=_fake_dl(archive=archive))
    assert outcome.udev_rules_path is None
    udev_dir = tm.store_root() / "udev"
    assert not (udev_dir / f"{artifact.tool}.rules").exists()


def test_udev_emission_never_invokes_sudo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the design contract: alloy-cli writes the
    rules but NEVER spawns a sudo process itself.
    """
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive, udev_rules="rules text\n")
    monkeypatch.setattr(tm.platform, "system", lambda: "Linux")

    spawned: list[tuple[str, ...]] = []

    real_popen = __import__("subprocess").Popen

    def _trap_popen(args, *a, **kw):  # type: ignore[no-untyped-def]
        if isinstance(args, (list, tuple)) and args and "sudo" in str(args[0]):
            spawned.append(tuple(args))
        return real_popen(args, *a, **kw)

    monkeypatch.setattr("subprocess.Popen", _trap_popen)

    tm.install(artifact, downloader=_fake_dl(archive=archive))
    assert spawned == [], f"sudo was invoked: {spawned}"


# ---------------------------------------------------------------------------
# zip support
# ---------------------------------------------------------------------------


def test_install_zip_archive(tmp_path: Path) -> None:
    archive = _make_zipball(tmp_path)
    artifact = SourceArtifact(
        tool="winfake",
        version="1.0",
        source="xpack",
        url=f"https://example.com/{archive.name}",
        sha256=_sha_of(archive.read_bytes()),
        archive_kind="zip",
        extract_to_subdir="",
        binaries=("bin/fake-gcc.exe",),
    )
    outcome = tm.install(artifact, downloader=_fake_dl(archive=archive))
    assert outcome.skipped is False
    assert (outcome.store_path / "bin/fake-gcc.exe").exists()


# ---------------------------------------------------------------------------
# Manifest atomicity
# ---------------------------------------------------------------------------


def test_manifest_written_atomically(tmp_path: Path) -> None:
    """After install, manifest.json exists and parses as JSON."""
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    manifest_path = tm.store_root() / tm.MANIFEST_NAME
    assert manifest_path.exists()
    import json

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == tm.MANIFEST_SCHEMA_VERSION
    assert len(payload["tools"]) == 1


def test_install_does_not_leave_manifest_tmp(tmp_path: Path) -> None:
    archive = _make_tarball(tmp_path)
    artifact = _artefact_for(archive)
    tm.install(artifact, downloader=_fake_dl(archive=archive))

    leftover = tm.store_root() / "manifest.json.tmp"
    assert not leftover.exists()


# ---------------------------------------------------------------------------
# store_root override via env var
# ---------------------------------------------------------------------------


def test_store_root_honours_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The autouse fixture already sets ALLOY_TOOLS_ROOT; verify
    `store_root()` resolves to it."""
    expected = Path(os.environ["ALLOY_TOOLS_ROOT"]).resolve()
    assert tm.store_root() == expected


def test_store_root_falls_back_to_platformdirs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the env override, store_root() uses platformdirs."""
    monkeypatch.delenv("ALLOY_TOOLS_ROOT")
    root = tm.store_root()
    assert root.name == "tools"
    assert "alloy" in str(root).lower()
