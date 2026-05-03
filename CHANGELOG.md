# Changelog

All notable changes to **alloy-cli** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Unreleased work lives at the top of the file; releases are tagged
``vX.Y.Z`` and published via ``.github/workflows/release.yml``.

## [Unreleased]

### Added — Wave-2 of toolchain-management

- **`add-toolchain-installer`** — alloy-cli now downloads, verifies-by-
  SHA256, extracts, and self-hosts every non-vendor tool a project's
  family declares.  No PATH munging: the content-addressed store at
  ``platformdirs.user_data_dir("alloy")/tools/`` holds the bytes;
  CMake / probe-rs / gdb invocations resolve absolute paths.
- New `alloy toolchain` command group with five verbs:
  ``install [--for <family>] [--shared] [--dry-run] [--include-optional]
  [--force]``, ``list [--installed/--missing] [--for <family>] [--json]``,
  ``use TOOL@VERSION``, ``prune [--dry-run] [--projects-root <dir>]``,
  ``shell [--print-path]``.  Vendor tools render the explicit
  "skipped (vendor — install manually: <URL>)" line; the installer
  never touches them.
- New JSON Schema ``schema/source_manifest_v1.json`` (Draft 2020-12)
  validating per-source-kind pin files.  Initial pin tables ship for
  xpack (arm-none-eabi-gcc 14.2.1, cmake 3.31.2, ninja 1.12.1),
  github (picotool, esptool, dfu-util, tio), probe-rs 0.27.0 with
  embedded udev rules, and Espressif (xtensa-esp-elf-gcc /
  riscv32-esp-elf-gcc 14.2.0).  All across 5 host triples (linux/
  macos/windows × x86_64/arm64) where upstream publishes them.
- New core modules:
    * ``core.tool_sources`` — ``XpackAdapter`` /
      ``GithubAdapter`` / ``ProbeRsAdapter`` / ``EspressifAdapter``
      behind a ``Source`` Protocol; ``Downloader`` Protocol with
      stdlib-urllib production + ``FakeDownloader`` test seam,
      streaming SHA256 verification on the wire.  ``host_triple()``
      with alias map (AMD64/aarch64/arm64e → canonical x86_64/arm64).
    * ``core.toolchain_manager`` — atomic install (download →
      SHA verify → extract → ``os.rename`` → symlink/pointer →
      manifest) under an advisory file lock (fcntl / msvcrt).
      ``resolve(tool, version, sha256)``, ``resolve_for_lockfile
      (project_root, tool)``, ``list_installed()``, ``verify()``,
      ``prune(projects=…)``, ``installed_bin_dirs()``,
      ``find_installed()``.  Honours ``ALLOY_TOOLS_ROOT`` env
      override for tests/CI.
    * ``core.lockfile_toolchain`` — read/write/dumps/parse/add/
      remove/diff for ``.alloy/toolchain.lock``.  Deterministic
      TOML, alphabetical key order, byte-stable across insert
      orders.
- ``core.build.run`` writes ``.alloy/cache/toolchain.cmake``
  whenever ``.alloy/toolchain.lock`` exists, stamp-keyed on
  ``sha256(lockfile) + alloy_cli_version``.  Compiler family map
  covers arm-none-eabi-gcc / xtensa-esp-elf-gcc /
  riscv32-esp-elf-gcc / riscv-none-elf-gcc.  Cmake configure now
  carries ``-DCMAKE_TOOLCHAIN_FILE=`` only when the lockfile is
  present — legacy projects keep building byte-identical to the
  pre-Wave-2 baseline.
- ``core.flash.run`` and ``core.debug.build_invocation`` resolve
  ``probe-rs`` / ``arm-none-eabi-gdb`` / xtensa+riscv variants via
  the lockfile + store before falling back to ``shutil.which``.
  Spawned argv carries the absolute store path; PATH stays the
  user's.
- New MCP read-only tools:
    * ``alloy.toolchain_status(family_id?)`` — Wave-1's
      ``list_family_toolchain`` enriched with installed /
      missing / vendor state from the local store.
    * ``alloy.toolchain_install_plan(family_id)`` — returns
      ``{plan, skipped_vendor, total_size_bytes}`` for the
      planned download set without performing any I/O.
- Linux udev handling: when a ``udev_required: true`` tool
  installs, the manager writes
  ``<base>/alloy/udev/<tool>.rules`` and emits the explicit
  ``sudo cp ... && sudo udevadm control --reload-rules``
  instruction.  alloy-cli never invokes ``sudo``.
- New typed errors under ``FamilyToolchainInstallerError``:
  ``checksum``, ``download``, ``extract``, ``store-corrupt``,
  ``version-mismatch``, ``unsupported-host``, ``locked``.  Each
  has a stable ``error_type`` string + a matching anchor in
  ``docs/ERROR_COOKBOOK.md``.
- New documentation: ``docs/TOOLCHAIN_INSTALLER.md`` covers the
  source adapter contract, the pin file format, the store layout,
  the lockfile workflow, the CMake toolchain file generation, the
  Linux udev story, and the trust model.
- New script ``scripts/refresh_source_pins.py`` walks every shipped
  pin file, recomputes SHAs from upstream, and updates the JSON in
  place.  Default is ``--dry-run`` (prints diff); ``--apply``
  writes.  Never opens a PR.
- 173 new tests across schema validation, tool_sources adapters,
  manager pipeline (atomic install + flock + prune + udev),
  lockfile read/write, CLI verbs, build CMake toolchain file
  integration, flash/debug lockfile resolution, MCP tools, and
  doc coverage.

### Added — Wave-1 of toolchain-management

- **`add-toolchain-registry`** — per-MCU-family declarative toolchain
  manifests under ``data/families/`` (validated by
  ``schema/family_toolchain_v1.json``).  Ships the
  ``arm-cortex-m`` shared base + five concrete families
  (``stm32f4``, ``stm32g0``, ``rp2040``, ``nrf52``, ``esp32``).
  Each manifest declares the required / recommended / optional
  tools for that family, with a closed ``source`` enum
  (``xpack`` / ``github:<owner>/<repo>`` / ``probe-rs-installer``
  / ``espressif`` / ``vendor``) so Wave-2's installer can
  dispatch without re-parsing.  Vendor-source tools carry per-OS
  ``install_docs`` URLs since EULA-gated binaries cannot be
  redistributed.
- ``core.toolchain_registry`` — typed loader resolving the
  ``extends:`` chain (cycle / unknown-parent detection), merging
  arrays by tool name, and caching parsed manifests on disk
  under ``.alloy/cache/families/`` keyed on
  sha256(yaml + parents + alloy-cli version).
- ``alloy doctor`` is now **family-aware**: when a project pins
  a known family (or ``--for <family>`` is passed), the toolchain
  check list comes from the matching manifest instead of the
  legacy generic set.  The rendered table grows a ``source``
  column; the JSON contract bumps ``schema_version`` to
  ``"1.1"`` and includes ``source`` on every entry.  Vendor
  tools surface as ``severity=info`` with the per-OS doc URL —
  never as errors, never as auto-fixable.
- ``alloy.list_family_toolchain(family_id)`` MCP tool exposes
  the same data to LLM agents (read-only; unknown families
  return a typed envelope with ``known_families``).
- New typed errors ``family-toolchain-{error,cycle,unknown-parent,
  schema,not-found}`` (all under ``AlloyCliError``); each carries
  a stable ``error_type`` string and a matching anchor in
  ``docs/ERROR_COOKBOOK.md``.
- ``docs/TOOLCHAIN_REGISTRY.md`` — contributor reference for
  the manifest format with the "add a new family" walkthrough.
- ``scripts/check_family_doc_links.py`` — opt-in URL canary
  (HEAD with GET fallback) for vendor ``install_docs``.
- 92 new tests across the schema, registry, family-aware
  diagnose, ``--for`` CLI flag, MCP tool, and contributor doc.

## [0.1.0] — 2026-05-02

First public release.  Wave-1 (15 OpenSpec proposals) shipped the
core surfaces; wave-2 (8 proposals) hardened them and brought
schema v1.1, snapshot testing, and a release runbook.

### Wave-1 — core surfaces

- **bootstrap-alloy-cli** — repo skeleton, ``alloy_cli`` package,
  Hatchling + hatch-vcs build, ``pyproject.toml``, ruff /
  pyright / pytest gates.
- **integrate-data-sources** — alloy-devices-yml submodule mount,
  IR projection cache (SHA-keyed), curated boards catalog,
  ``alloy boards`` + ``alloy devices`` searches.
- **define-project-format** — ``alloy.toml`` v1.0 schema +
  validator + deterministic emitter, ``ProjectConfig`` typed
  view, scaffold helpers.
- **add-cli-new** — ``alloy new`` with templates, board-aware
  defaults, generated CMake bridge.
- **add-cli-add-peripheral** — typed ``add_uart`` /
  ``add_spi`` / ``add_i2c`` / ``add_gpio`` operations + the
  ``alloy add`` CLI surface.
- **add-cli-build-flash-debug** — toolchain detection,
  ``alloy build`` / ``alloy flash`` / ``alloy debug``,
  cached metadata under ``.alloy/``.
- **add-tui-foundation** — Textual app shell, command
  palette, screen registry, theme, value widgets.
- **add-tui-dashboard-and-onboarding** — Dashboard +
  Onboarding screens with toolchain pills, recent activity,
  and memory bars.
- **add-tui-board-picker** — full BoardPicker with search,
  filters, and arrow-key navigation.
- **add-tui-peripheral-assignment** — Peripheral Add screen
  with the PinoutWidget candidate / assigned highlighting.
- **add-tui-clock-tree-and-build-flash** — Clock Tree,
  Build Log, and Flash screens.
- **add-mcp-server** — MCP tool registry, stdio fallback,
  preview / apply diff cache, ``alloy.preview_diff`` /
  ``alloy.apply_diff`` entry points.
- **add-doctor-update-export** — host diagnostics, lockfile
  cache, ``alloy doctor`` / ``alloy update`` / ``alloy
  export``.
- **recommend-opencode-host** — opencode integration recipe
  + system prompt under ``src/alloy_cli/integrations/opencode/``.

### Wave-2 — hardening + reach

- **add-codegen-integration** — alloy-codegen pre-build
  step with stamp-based caching (IR SHA + version pinning),
  ``--regen`` / ``--no-codegen`` build flags, ``alloy.regenerate``
  MCP tool.
- **enrich-peripheral-kinds** — schema v1.1 with typed
  timer / pwm / adc / dac / can / usb / eth, auto-DMA channel
  allocation in uart / spi / i2c, 7 new ``alloy add`` subcommands
  + MCP wrappers.
- **add-real-update-pipeline** — ``UpgradeReport`` /
  ``ComponentUpgrader`` typed callable, dependency-ordered
  atomic upgrades with rollback, ``pip``-/``git``-backed
  upgrader registry.
- **add-clock-profile-persistence** — ``[clocks].profiles`` map
  in alloy.toml, ``ClockTreeScreen.action_save_profile`` flow,
  ``alloy.save_clock_profile`` / ``alloy.activate_clock_profile``
  MCP tools.
- **add-tui-doctor-screen** — interactive ``DoctorScreen`` with
  ``r`` re-run / ``f`` auto-fix / per-row detail; ``alloy doctor
  --fix`` non-interactive mode for container warm-up.
- **add-tui-package-pinout** — per-package perimeter
  rendering (LQFP / QFN / BGA / WLCSP / SOIC / DIP / TSSOP),
  ``alloy boards <id> --pinout`` read-only TUI session.
- **add-snapshot-test-harness** — ``tests/snapshots/`` SVG
  goldens for every shipped TUI screen + key CLI snippets,
  ``--snapshot-update`` refresh flag, byte-stable ``docs/images/``.
- **harden-release-and-injection** — single-canonical
  ``core.project.dumps`` emitter, public ``ToolRegistry`` /
  ``ScreenRegistry`` APIs, injection-seam regression test,
  ``docs/RELEASING.md`` runbook, HIL CI workflow.

[Unreleased]: https://github.com/Alloy-Embedded/alloy-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Alloy-Embedded/alloy-cli/releases/tag/v0.1.0
