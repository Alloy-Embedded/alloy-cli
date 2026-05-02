## 1. Source pin schema + initial pin files

- [ ] 1.1 Author `schema/source_manifest_v1.json` (Draft 2020-12) with `additionalProperties: false` at every level, the closed `archive_kind` enum (`tar.xz`, `tar.gz`, `zip`, `bin`), the closed `source` enum, the per-host `<os>-<arch>` pattern, and the conditional that vendor source is rejected.
- [ ] 1.2 Add `tests/test_source_manifest_schema.py` exercising the schema with a hand-rolled valid pin file plus at least four negative fixtures (missing `schema_version`, unknown `source`, vendor source present, unsupported `archive_kind`).
- [ ] 1.3 Author `data/sources/xpack.json` with pins for arm-none-eabi-gcc 14.2.0 + cmake 3.31 + ninja 1.12 across `linux-x86_64`, `linux-arm64`, `macos-x86_64`, `macos-arm64`, `windows-x86_64`.  Include only releases the contributor can verify by SHA256 from the upstream xpack release feed.
- [ ] 1.4 Author `data/sources/github.json` with pins for picotool 2.0.0, esptool 4.7.0, dfu-util 0.11, tio 2.7.0 (host-aware where the upstream ships per-OS assets).
- [ ] 1.5 Author `data/sources/probe-rs.json` with the probe-rs 0.27.0 release for the five host triples plus the udev rules content shipped in the same upstream release tarball.
- [ ] 1.6 Author `data/sources/espressif.json` with xtensa-esp-elf-gcc 14.2.0 + riscv32-esp-elf-gcc 14.2.0 from the Espressif idf-tools index (linux-x86_64 / macos-x86_64 / macos-arm64 / windows-x86_64; document `unsupported_hosts` for any host the upstream lacks).
- [ ] 1.7 Wire every new file into `pyproject.toml`'s `shared-data` and `force-include` blocks so they ship inside the wheel.

## 2. `core.tool_sources` adapters + Downloader protocol

- [ ] 2.1 Add the seven `FamilyToolchainInstaller*Error` types to `src/alloy_cli/core/errors.py`; export them from `__all__`; extend the existing uniqueness test.
- [ ] 2.2 Add cookbook anchors to `docs/ERROR_COOKBOOK.md` for each new `family-toolchain-installer-*` error type so `scripts/check_error_cookbook.py` stays green.
- [ ] 2.3 Create `src/alloy_cli/core/tool_sources.py` with frozen+slots dataclasses `HostTriple`, `SourceArtifact`, plus a `Source` Protocol and a `Downloader` Protocol.
- [ ] 2.4 Implement `host_triple()` returning the active `(os, arch)` from `platform.system()` + `platform.machine()`, raising `family-toolchain-installer-unsupported-host` for unknown combinations.
- [ ] 2.5 Implement a `_load_pins(source_kind)` helper that mirrors `core.project._load_schema` (try repo path first, fall back to wheel data via `importlib.resources`) and JSON-Schema-validates the file at load time.
- [ ] 2.6 Implement `XpackAdapter`, `GithubAdapter`, `ProbeRsAdapter`, `EspressifAdapter` — each consumes its pin file, exposes `.resolve(tool, host) -> SourceArtifact`, raises `family-toolchain-installer-unsupported-host` for unsupported triples.
- [ ] 2.7 Implement the `adapter_for(source: str)` dispatcher that maps prefixes (`xpack`, `github:`, `probe-rs-installer`, `espressif`) to the right adapter and rejects `vendor` with the typed error.
- [ ] 2.8 Implement `_RealDownloader` (urllib.request, streaming SHA256 verification, single retry with backoff, configurable user-agent string) and `FakeDownloader` (test seam that copies fixture files into `dest`).
- [ ] 2.9 Add `tests/test_tool_sources.py` covering: every shipped pin file loads, `host_triple()` returns correct values via monkeypatch on `platform.*`, every adapter resolves a known pin for the active host, missing host raises the typed error, the dispatcher routes every prefix to the right adapter, vendor source is rejected, `FakeDownloader` round-trips a fixture into a destination.

## 3. `core.toolchain_manager` content-addressed store + lockfile

- [ ] 3.1 Create `src/alloy_cli/core/toolchain_manager.py` with frozen+slots dataclasses `InstalledTool`, `InstallOutcome`, `PruneReport`.
- [ ] 3.2 Implement `_store_root()` resolving `platformdirs.user_data_dir("alloy") / "tools"`; expose helpers `_store_subdir(sha)`, `_by_name(tool, version)`, `_manifest_path()`, `_lock_path()`, `_udev_dir()`.
- [ ] 3.3 Implement `_acquire_lock()` / `_release_lock()` using `fcntl.flock(LOCK_EX | LOCK_NB)` on POSIX and `msvcrt.locking` on Windows; raise `family-toolchain-installer-locked` when held by another process.
- [ ] 3.4 Implement atomic install: stream download to `store/.tmp/<sha>.partial`, verify SHA256 on the wire, extract to `store/.tmp/<sha>/` (use `tarfile.data_filter` on Python 3.12+; manual sanitiser on older Pythons), `os.rename` to `store/<sha>/`, drop a symlink/pointer at `by-name/<tool>/<version>`, update `manifest.json` under the same lock.
- [ ] 3.5 Implement Linux udev handling: when a tool's family manifest declares `udev_required: true` AND the active host is Linux, write the rules to `<base>/alloy/udev/<tool>.rules` and emit the explicit `sudo cp ... && sudo udevadm control --reload-rules` instruction via `on_line`.  NEVER invoke sudo.
- [ ] 3.6 Implement `resolve(tool_name, version=None) -> Path | None` that walks `manifest.json` + `by-name/` and returns the absolute path to the primary binary (handle bundled binaries via `FamilyManifest.find_tool().bundles`).
- [ ] 3.7 Implement `list_installed() -> list[InstalledTool]` reading `manifest.json` and computing `size_bytes` per entry on demand.
- [ ] 3.8 Implement `verify(tool_name) -> bool` running SHA256 over the on-disk extraction tree and comparing against the manifest entry; return False when the store is corrupt.
- [ ] 3.9 Implement `prune(*, projects: Sequence[Path], dry_run: bool = False) -> PruneReport` that reads every `.alloy/toolchain.lock` under the supplied project roots, builds the union of pinned `(tool, version, sha)` triples, and removes / lists every store entry not in that union.
- [ ] 3.10 Implement `core.lockfile_toolchain` with `read(path)`, `write(path, lock)`, `add(lock, tool, version, sha256)`, `remove(lock, tool)`, `dumps(lock)` (deterministic TOML, single emitter).
- [ ] 3.11 Add `tests/test_toolchain_manager.py` covering: install on a fresh store with `FakeDownloader` succeeds, install verifies SHA (negative fixture: pre-corrupted bytes), re-install is a no-op, two installs in parallel raise `family-toolchain-installer-locked`, store corruption surfaces typed errors, resolve handles bundled binaries, prune dry-run lists candidates, prune deletes only unreferenced versions, udev rules emitted on Linux are written without sudo invocation.
- [ ] 3.12 Add `tests/test_lockfile_toolchain.py` covering: round-trip read/write, alphabetical key order on add, invalid TOML raises ProjectConfigError, dumps is byte-stable.

## 4. `alloy toolchain` Click command group

- [ ] 4.1 Create `src/alloy_cli/commands/toolchain.py` with the Click group + five subcommands (`install`, `list`, `use`, `prune`, `shell`).
- [ ] 4.2 Wire family resolution: every subcommand accepts `--for <family>` (validated against `toolchain_registry.known_families()`) and falls back to `resolve_for_project(config)` when omitted; missing family + missing `--for` exits non-zero with a clear message.
- [ ] 4.3 Implement `install` orchestration: gather the family's required + non-vendor recommended tools, dispatch each to `tool_sources.adapter_for(...)`, hand the artefacts to `toolchain_manager.install(...)`, update `.alloy/toolchain.lock` (unless `--shared`), print a Rich table with progress bars (download size + extraction).  Honour `--dry-run` by short-circuiting before the downloader runs.
- [ ] 4.4 Implement `list` (Rich table by default, JSON behind `--json`); cross-reference store state via `toolchain_manager.list_installed()` + the family manifest.
- [ ] 4.5 Implement `use <tool>@<version>` — locate the matching pin in the source files, write `(tool, version, sha256)` into `.alloy/toolchain.lock`, refuse to pin a tool not in any pin file with a clear message naming the available versions.
- [ ] 4.6 Implement `prune [--dry-run]` — discover sibling projects via the platform-data project registry (or a `--projects-root` flag), call `toolchain_manager.prune(...)`, render bytes recovered.
- [ ] 4.7 Implement `shell` — augment `PATH` with every installed bin directory, `os.execvpe($SHELL, ...)` on POSIX, `subprocess.call(["cmd.exe", "/K"])` on Windows; ensure exiting the subshell leaves the parent unchanged.
- [ ] 4.8 Register the new group in `src/alloy_cli/main.py` (`cli.add_command(toolchain_command)`).
- [ ] 4.9 Run `python scripts/generate_cheatsheet.py` so the new commands land in `docs/CHEATSHEET.md`; confirm CI's cheatsheet check stays green.
- [ ] 4.10 Add `tests/test_command_toolchain.py` covering: `--dry-run` prints the plan + writes nothing, `--for nonexistent` exits non-zero with the available list, vendor tools render the explicit "skipped (vendor — install manually: ...)" line, `list --json` reports installed + missing per family, `use <tool>@<version>` updates the lockfile in place, `prune --dry-run` lists candidates without deleting, `shell` augments PATH inside the spawned subshell only.

## 5. CMake toolchain file generation in `core.build`

- [ ] 5.1 Extend `core.build.run` to read `.alloy/toolchain.lock` (when present) and resolve every tool path via `toolchain_manager.resolve(...)`; raise `family-toolchain-installer-version-mismatch` when any pinned tool is missing from the store.
- [ ] 5.2 Implement `_generate_toolchain_cmake(layout, lockfile_text, alloy_cli_version)` writing `.alloy/cache/toolchain.cmake` with the absolute compiler / ar / ranlib paths and a stamp (`<file>.stamp` carrying `lockfile_sha + alloy_cli_version`).  Skip regeneration when the stamp matches.
- [ ] 5.3 Pass `-DCMAKE_TOOLCHAIN_FILE=` to the cmake configure invocation when the lockfile is present; do NOT pass it when the lockfile is absent (legacy projects keep building).
- [ ] 5.4 Add the toolchain stamp to the codegen+cmake invalidation path so a lockfile change forces a fresh configure.
- [ ] 5.5 Update `tests/test_build.py` (existing) with two new tests: `alloy build` on a project with `.alloy/toolchain.lock` writes the toolchain file + passes the cmake flag; the same project rebuilt without lockfile changes does NOT rewrite the file.
- [ ] 5.6 Add a regression test asserting `alloy build` on a project WITHOUT `.alloy/toolchain.lock` keeps today's invocation byte-identical (no `-DCMAKE_TOOLCHAIN_FILE`).

## 6. Flash + debug binary resolution via the store

- [ ] 6.1 Update `core.flash.run` to resolve `probe-rs` via `toolchain_manager.resolve(...)` first, falling back to `shutil.which` when the lockfile is missing OR the resolution returns `None`.  Raise `family-toolchain-installer-version-mismatch` when the lockfile pins a probe-rs version not in the store.
- [ ] 6.2 Update `core.debug.build_invocation` to resolve `arm-none-eabi-gdb` (and the riscv / xtensa equivalents when the family manifest declares them) the same way.
- [ ] 6.3 Update tests in `tests/test_flash.py` + `tests/test_debug.py` to assert: when the store has the locked probe-rs / gdb, the spawned argv begins with the absolute store path; when the lockfile is missing, behaviour is byte-identical to today.

## 7. MCP read-only tools

- [ ] 7.1 Add `_tool_toolchain_status` handler in `src/alloy_cli/mcp/tools.py` enriching Wave 1's `list_family_toolchain` projection with `installed / installed_version / installed_path / state` per tool from `toolchain_manager.list_installed()`.
- [ ] 7.2 Add `_tool_toolchain_install_plan` handler dispatching every non-vendor tool to its adapter (no network — adapters return the pinned `SourceArtifact`), emitting the plan + skipped-vendor list + total size.  Trap `FamilyToolchainInstallerUnsupportedHostError` and surface a typed envelope with the host triple + supported_hosts.
- [ ] 7.3 Register both tools in `_PARAM_SCHEMA` (`{"family_id": "string"}` for `toolchain_install_plan`; `{"family_id": "string?"}` for `toolchain_status`) and in `build_default_registry`'s handler dict.
- [ ] 7.4 Add `tests/test_mcp_toolchain.py` covering: `toolchain_status` reports installed vs missing, `toolchain_install_plan` returns the plan + `skipped_vendor` array, unknown family returns the Wave 1 envelope, unsupported host returns the new envelope, both tools appear in the registry's discoverable name set, neither tool calls the downloader.

## 8. Documentation

- [ ] 8.1 Author `docs/TOOLCHAIN_INSTALLER.md` — covers the source adapter contract, the pin file format, the store layout, the lockfile format + workflow, the CMake toolchain file generation, the udev rules emission, the trust model.  Cross-link to `docs/TOOLCHAIN_REGISTRY.md` (Wave 1) and `docs/ERROR_COOKBOOK.md`.
- [ ] 8.2 Author `scripts/refresh_source_pins.py` — fetches each upstream's release feed, computes SHA256 from the actual asset, regenerates `data/sources/*.json`.  Defaults to `--dry-run` (prints the diff); `--apply` writes; never opens a PR automatically.
- [ ] 8.3 Add `tests/test_toolchain_installer_doc.py` mirroring Wave 1's `test_toolchain_registry_doc.py`: assert every shipped schema field is documented, every error type has a cookbook anchor, the "add a new source" walkthrough mentions the right test commands.
- [ ] 8.4 Update `docs/CHEATSHEET.md` (regen step 4.9 already covers this, but verify the new `alloy toolchain *` entries are present).

## 9. Validation + ship-readiness

- [ ] 9.1 Run `openspec validate add-toolchain-installer --strict` and resolve every reported issue.
- [ ] 9.2 Run the targeted test files locally and confirm green: `pytest tests/test_source_manifest_schema.py tests/test_tool_sources.py tests/test_toolchain_manager.py tests/test_lockfile_toolchain.py tests/test_command_toolchain.py tests/test_mcp_toolchain.py tests/test_toolchain_installer_doc.py`.
- [ ] 9.3 Run `pytest -q --deselect tests/test_mcp_server.py::test_alloy_mcp_serve_stdio_round_trips_via_subprocess` (or the equivalent CI matrix subset) and confirm green.
- [ ] 9.4 Run `ruff check src tests scripts` and `pyright src/alloy_cli` — fix any new findings.
- [ ] 9.5 Update `CHANGELOG.md` under `[Unreleased]` with a Wave-2 entry naming the new capability, the `alloy toolchain` group, the CMake toolchain file generation, and the two MCP tools.
- [ ] 9.6 Open the PR titled `Implement add-toolchain-installer (Wave 2 of toolchain-management)` referencing this OpenSpec change in the description.
