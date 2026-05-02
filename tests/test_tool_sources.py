"""Tests for ``core.tool_sources``.

Covers:
  * `host_triple()` resolution + alias map + unsupported-host error.
  * `_load_pins()` validates against the schema and caches.
  * Every shipped pin file resolves a known tool for the active host.
  * Each adapter raises `family-toolchain-installer-unsupported-host`
    for missing host pins (and respects the `unsupported_hosts`
    declaration).
  * The dispatcher routes every prefix to the right adapter and
    rejects vendor.
  * `_RealDownloader` is constructible (network call exercised in
    the FakeDownloader path).
  * `FakeDownloader` round-trips a fixture into a destination AND
    raises the typed checksum error when the fixture's SHA differs
    from the artefact pin.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from alloy_cli.core import tool_sources as ts
from alloy_cli.core.errors import (
    FamilyToolchainInstallerChecksumError,
    FamilyToolchainInstallerDownloadError,
    FamilyToolchainInstallerError,
    FamilyToolchainInstallerUnsupportedHostError,
    FamilyToolchainSchemaError,
)
from alloy_cli.core.toolchain_registry import ToolRequirement

# ---------------------------------------------------------------------------
# host_triple()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("system", "machine", "expected_os", "expected_arch"),
    [
        ("Darwin", "arm64", "macos", "arm64"),
        ("Darwin", "x86_64", "macos", "x86_64"),
        ("Darwin", "arm64e", "macos", "arm64"),
        ("Linux", "x86_64", "linux", "x86_64"),
        ("Linux", "aarch64", "linux", "arm64"),
        ("Windows", "AMD64", "windows", "x86_64"),
        ("Windows", "amd64", "windows", "x86_64"),
        ("Windows", "ARM64", "windows", "arm64"),
    ],
)
def test_host_triple_recognised_combinations(
    system: str,
    machine: str,
    expected_os: str,
    expected_arch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ts.platform, "system", lambda: system)
    monkeypatch.setattr(ts.platform, "machine", lambda: machine)
    triple = ts.host_triple()
    assert triple.os == expected_os
    assert triple.arch == expected_arch
    assert str(triple) == f"{expected_os}-{expected_arch}"


def test_host_triple_unsupported_os_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts.platform, "system", lambda: "FreeBSD")
    monkeypatch.setattr(ts.platform, "machine", lambda: "x86_64")
    with pytest.raises(FamilyToolchainInstallerUnsupportedHostError) as exc:
        ts.host_triple()
    assert "FreeBSD" in str(exc.value)


def test_host_triple_unsupported_arch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ts.platform, "machine", lambda: "mips64")
    with pytest.raises(FamilyToolchainInstallerUnsupportedHostError) as exc:
        ts.host_triple()
    assert "mips64" in str(exc.value)


# ---------------------------------------------------------------------------
# _load_pins
# ---------------------------------------------------------------------------


def test_known_source_kinds_matches_dispatcher() -> None:
    assert set(ts.known_source_kinds()) == {"espressif", "github", "probe-rs", "xpack"}


@pytest.mark.parametrize("kind", ["xpack", "github", "probe-rs", "espressif"])
def test_load_pins_for_each_shipped_source(kind: str) -> None:
    payload = ts._load_pins(kind)
    assert payload["source"] == kind
    assert payload["schema_version"] == "1.0.0"
    assert isinstance(payload["tools"], list)
    assert payload["tools"], f"{kind}.json must declare at least one tool"


def test_load_pins_unknown_source_raises() -> None:
    with pytest.raises(FamilyToolchainInstallerError) as exc:
        ts._load_pins("homebrew")
    assert "homebrew" in str(exc.value)


def test_load_pins_caches_per_kind() -> None:
    """Two calls return the same dict (cached via lru_cache)."""
    a = ts._load_pins("xpack")
    b = ts._load_pins("xpack")
    assert a is b


def test_load_pins_validates_against_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed pin payload surfaces a typed schema error.

    We can't actually mutate the shipped JSON, so we monkeypatch the
    text reader to return a deliberately broken payload and expect the
    validator to fire.
    """
    ts._load_pins.cache_clear()
    monkeypatch.setattr(
        ts,
        "_read_pin_text",
        lambda _filename: '{"schema_version": "1.0.0", "source": "xpack", "tools": []}',
    )
    with pytest.raises(FamilyToolchainSchemaError) as exc:
        ts._load_pins("xpack")
    assert "minItems" in str(exc.value) or "tools" in str(exc.value)
    ts._load_pins.cache_clear()  # restore for subsequent tests


# ---------------------------------------------------------------------------
# Adapter resolve()
# ---------------------------------------------------------------------------


def _arm_gcc_req() -> ToolRequirement:
    return ToolRequirement(
        tool="arm-none-eabi-gcc",
        version=">=13,<16",
        source="xpack",
        capabilities=("build", "debug"),
    )


def _esp_gcc_req() -> ToolRequirement:
    return ToolRequirement(
        tool="xtensa-esp-elf-gcc",
        version=">=14",
        source="espressif",
        capabilities=("build", "debug"),
    )


def _picotool_req() -> ToolRequirement:
    return ToolRequirement(
        tool="picotool",
        version=">=2.0",
        source="github:raspberrypi/picotool",
        capabilities=("flash", "reset"),
    )


def _probe_rs_req() -> ToolRequirement:
    return ToolRequirement(
        tool="probe-rs",
        version=">=0.27",
        source="probe-rs-installer",
        capabilities=("flash", "debug", "reset"),
    )


def test_xpack_adapter_resolves_arm_gcc_for_macos_arm64() -> None:
    adapter = ts.XpackAdapter()
    artifact = adapter.resolve(_arm_gcc_req(), ts.HostTriple(os="macos", arch="arm64"))
    assert artifact.tool == "arm-none-eabi-gcc"
    assert artifact.source == "xpack"
    assert artifact.archive_kind == "tar.gz"
    assert artifact.url.startswith("https://github.com/xpack-dev-tools/")
    assert "darwin-arm64" in artifact.url
    assert artifact.primary_binary == "bin/arm-none-eabi-gcc"
    assert "bin/arm-none-eabi-gdb" in artifact.binaries
    # SHA placeholder is 64 hex zeros while pins are pending verification
    assert artifact.sha256 == "0" * 64


def test_xpack_adapter_resolves_for_every_canonical_host() -> None:
    adapter = ts.XpackAdapter()
    for os_id in ("linux", "macos", "windows"):
        for arch in ("x86_64", "arm64"):
            if os_id == "windows" and arch == "arm64":
                continue  # not in the seed pin set
            triple = ts.HostTriple(os=os_id, arch=arch)
            artifact = adapter.resolve(_arm_gcc_req(), triple)
            assert artifact.tool == "arm-none-eabi-gcc"
            # archive_kind reflects the OS convention
            if os_id == "windows":
                assert artifact.archive_kind == "zip"
            else:
                assert artifact.archive_kind == "tar.gz"


def test_github_adapter_resolves_picotool() -> None:
    adapter = ts.GithubAdapter()
    artifact = adapter.resolve(_picotool_req(), ts.HostTriple(os="macos", arch="arm64"))
    assert artifact.tool == "picotool"
    assert artifact.source == "github"
    assert "raspberrypi/pico-sdk-tools" in artifact.url


def test_probe_rs_adapter_carries_udev_rules() -> None:
    adapter = ts.ProbeRsAdapter()
    artifact = adapter.resolve(
        _probe_rs_req(), ts.HostTriple(os="linux", arch="x86_64")
    )
    assert artifact.tool == "probe-rs"
    assert artifact.source == "probe-rs"
    assert "ATTRS{idVendor}" in artifact.udev_rules
    assert "0483" in artifact.udev_rules  # ST-Link VID


def test_probe_rs_udev_rules_propagate_for_every_host() -> None:
    """The udev rules text comes from the tool entry, not the per-host
    block — so every host triple's artefact carries the same rules.
    """
    adapter = ts.ProbeRsAdapter()
    for triple in (
        ts.HostTriple(os="linux", arch="x86_64"),
        ts.HostTriple(os="macos", arch="arm64"),
        ts.HostTriple(os="windows", arch="x86_64"),
    ):
        artifact = adapter.resolve(_probe_rs_req(), triple)
        assert artifact.udev_rules, f"udev_rules empty for {triple}"


def test_espressif_adapter_resolves_xtensa_gcc() -> None:
    adapter = ts.EspressifAdapter()
    artifact = adapter.resolve(_esp_gcc_req(), ts.HostTriple(os="macos", arch="arm64"))
    assert artifact.tool == "xtensa-esp-elf-gcc"
    assert artifact.source == "espressif"
    assert "esp-14.2.0_20240906" in artifact.url


def test_espressif_adapter_unsupported_host_for_linux_arm64() -> None:
    """linux-arm64 is in the unsupported_hosts list — error message
    must distinguish 'not pinned yet' from 'upstream doesn't ship'.
    """
    adapter = ts.EspressifAdapter()
    with pytest.raises(FamilyToolchainInstallerUnsupportedHostError) as exc:
        adapter.resolve(_esp_gcc_req(), ts.HostTriple(os="linux", arch="arm64"))
    msg = str(exc.value)
    assert "unsupported_hosts" in msg
    assert "linux-arm64" in msg


def test_xpack_adapter_unknown_tool_raises() -> None:
    adapter = ts.XpackAdapter()
    bogus = ToolRequirement(
        tool="not-a-real-tool",
        version=">=1",
        source="xpack",
        capabilities=("build",),
    )
    with pytest.raises(FamilyToolchainInstallerUnsupportedHostError) as exc:
        adapter.resolve(bogus, ts.HostTriple(os="macos", arch="arm64"))
    assert "not-a-real-tool" in str(exc.value)


def test_xpack_adapter_kind_property() -> None:
    assert ts.XpackAdapter().kind == "xpack"
    assert ts.GithubAdapter().kind == "github"
    assert ts.ProbeRsAdapter().kind == "probe-rs"
    assert ts.EspressifAdapter().kind == "espressif"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_dispatcher_routes_every_prefix() -> None:
    assert isinstance(ts.adapter_for("xpack"), ts.XpackAdapter)
    assert isinstance(ts.adapter_for("probe-rs-installer"), ts.ProbeRsAdapter)
    assert isinstance(ts.adapter_for("espressif"), ts.EspressifAdapter)
    assert isinstance(ts.adapter_for("github:tio/tio"), ts.GithubAdapter)
    assert isinstance(
        ts.adapter_for("github:raspberrypi/picotool"), ts.GithubAdapter
    )


def test_dispatcher_rejects_vendor() -> None:
    with pytest.raises(FamilyToolchainInstallerUnsupportedHostError) as exc:
        ts.adapter_for("vendor")
    assert "EULA" in str(exc.value) or "vendor" in str(exc.value).lower()


def test_dispatcher_rejects_unknown_source() -> None:
    with pytest.raises(FamilyToolchainInstallerError) as exc:
        ts.adapter_for("homebrew")
    assert "homebrew" in str(exc.value)


def test_dispatcher_returns_source_protocol_conformant() -> None:
    """Every adapter satisfies the runtime-checkable Source protocol."""
    for source in (
        "xpack",
        "github:foo/bar",
        "probe-rs-installer",
        "espressif",
    ):
        adapter = ts.adapter_for(source)
        assert isinstance(adapter, ts.Source)


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------


def _sha_of(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def _make_artefact(*, url: str, sha: str, archive_kind: str = "tar.gz") -> ts.SourceArtifact:
    return ts.SourceArtifact(
        tool="fake",
        version="1.0",
        source="xpack",
        url=url,
        sha256=sha,
        archive_kind=archive_kind,
        extract_to_subdir="",
        binaries=("bin/fake",),
    )


def test_fake_downloader_round_trips_fixture(tmp_path: Path) -> None:
    src = tmp_path / "src.tar.gz"
    body = b"hello world"
    src.write_bytes(body)
    sha = _sha_of(body)

    artifact = _make_artefact(url="https://example.com/x.tar.gz", sha=sha)
    fake = ts.FakeDownloader()
    fake.expect("https://example.com/x.tar.gz", src)

    dest = tmp_path / "dest.tar.gz"
    out = fake.fetch(artifact, dest)
    assert out == dest
    assert dest.read_bytes() == body
    # Single recorded call
    assert len(fake.calls) == 1
    assert fake.calls[0].url == artifact.url


def test_fake_downloader_checksum_mismatch_raises(tmp_path: Path) -> None:
    """SHA path runs honestly even on the fake — a fixture whose
    bytes don't match the pinned SHA must surface the typed
    checksum error.
    """
    src = tmp_path / "src.tar.gz"
    src.write_bytes(b"genuinely different bytes")

    artifact = _make_artefact(
        url="https://example.com/x.tar.gz",
        sha="0" * 64,  # placeholder that doesn't match the actual bytes
    )
    fake = ts.FakeDownloader()
    fake.expect("https://example.com/x.tar.gz", src)

    dest = tmp_path / "dest.tar.gz"
    with pytest.raises(FamilyToolchainInstallerChecksumError) as exc:
        fake.fetch(artifact, dest)
    assert "SHA256 mismatch" in str(exc.value)
    # Partial file was cleaned up
    partial = dest.with_suffix(dest.suffix + ".partial")
    assert not partial.exists()
    assert not dest.exists()


def test_fake_downloader_missing_fixture_raises_typed_error(tmp_path: Path) -> None:
    artifact = _make_artefact(url="https://example.com/x.tar.gz", sha="0" * 64)
    fake = ts.FakeDownloader()
    # No expect() registration

    dest = tmp_path / "dest.tar.gz"
    with pytest.raises(FamilyToolchainInstallerDownloadError) as exc:
        fake.fetch(artifact, dest)
    assert "FakeDownloader" in str(exc.value)


def test_fake_downloader_progress_callback_invoked(tmp_path: Path) -> None:
    """Progress callback fires at least once during the streaming
    SHA path — important for `alloy toolchain install` UI."""
    src = tmp_path / "src.bin"
    body = b"x" * (128 * 1024)  # 128 KiB → 2 chunks of 64 KiB
    src.write_bytes(body)
    sha = _sha_of(body)
    artifact = _make_artefact(url="https://example.com/big.bin", sha=sha, archive_kind="bin")

    fake = ts.FakeDownloader()
    fake.expect("https://example.com/big.bin", src)

    progress: list[tuple[int, int | None]] = []
    fake.fetch(
        artifact,
        tmp_path / "out.bin",
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert progress, "progress callback must be invoked at least once"
    # Final call should report total bytes
    assert progress[-1][0] == len(body)
    assert progress[-1][1] == len(body)


def test_configure_downloader_swap_and_restore() -> None:
    fake = ts.FakeDownloader()
    original = ts.downloader
    restore = ts.configure_downloader(fake)
    try:
        assert ts.downloader is fake
    finally:
        restore()
    assert ts.downloader is original


def test_real_downloader_is_module_default() -> None:
    """Just sanity: the module's default downloader is the production
    one (tests opt into the fake explicitly)."""
    assert isinstance(ts.downloader, ts._RealDownloader)


# ---------------------------------------------------------------------------
# file_sha256 helper
# ---------------------------------------------------------------------------


def test_file_sha256_matches_hashlib(tmp_path: Path) -> None:
    body = b"some bytes for the canary"
    f = tmp_path / "x"
    f.write_bytes(body)
    assert ts.file_sha256(f) == _sha_of(body)


def test_file_sha256_handles_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty"
    f.write_bytes(b"")
    # SHA256 of empty input is well-known
    assert ts.file_sha256(f) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
