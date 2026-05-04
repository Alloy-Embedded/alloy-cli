# Changelog

All notable changes to **alloy-cli** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Unreleased work lives at the top of the file; releases are tagged
``vX.Y.Z`` and published via ``.github/workflows/release.yml``.

## [Unreleased]

### Added — Documentation site

- **`add-docs-site`** — alloy-cli now ships a professional
  GitHub Pages documentation site at
  [alloy-embedded.github.io/alloy-cli](https://alloy-embedded.github.io/alloy-cli/).
  Built with **MkDocs Material**; deployed via
  `.github/workflows/docs.yml` on every push to `main` and every
  `v*` tag.  Decoupled from `release.yml` so a docs-only change
  does not trigger a PyPI publish.
- **Information architecture**: Home / Getting Started / User
  Guide / Reference / Concepts / Architecture & Design /
  Contributing / API Reference / Changelog.  Every existing
  `docs/*.md` file is reachable through the new nav; no file
  moves.
- **Auto-generated CLI reference** via `mkdocs-click` against
  `alloy_cli.main:cli`.  Every `alloy <verb>` (all 18 commands)
  surfaces automatically; adding a new Click command lands in
  the docs on the next build.
- **Auto-generated API reference** via `mkdocstrings[python]`
  for `alloy_cli.core.{toolchain_orchestrator,probe_orchestrator,
  toolchain_registry,tool_sources,errors}`, `alloy_cli.mcp`,
  and the TUI screens.  Private symbols filtered out.
- **5 new concept docs** under `docs/concepts/` (~80–130 lines
  each): Device IR, Toolchain orchestrator (with Mermaid
  diagram), Probe orchestrator (with Mermaid diagram),
  Lockfile-aware execution, Two-phase mutations.
- **2 new Getting Started pages**: Installation (system
  requirements + extras matrix), Your first project (deep
  walkthrough beyond the 5-min QUICKSTART).
- **URL stability via `mkdocs-redirects`**: every existing
  `docs/<X>.md` URL keeps resolving (source files didn't move),
  plus user-friendly aliases (`/quickstart/`, `/recovery/`,
  `/cookbook/`, `/cheatsheet/`) + future-IA paths
  (`/getting-started/quickstart/`, `/user-guide/recovery/`,
  etc.) for external link compatibility.
- **`pip install -e .[docs]`** new optional-deps group
  (mkdocs + mkdocs-material + mkdocstrings[python] +
  mkdocs-click + mkdocs-redirects + mkdocs-include-markdown +
  pymdown-extensions).  Runtime install footprint unchanged.
- **Custom theming**: alloy-blue (Material indigo) + amber
  accent (deep-orange) palette matching the TUI snapshots,
  custom CSS for hero card / TUI snapshot framing / Mermaid
  diagrams / print-friendly overrides, SVG wordmark logo +
  favicon.  Light + dark palette with toggle persisting via
  `localStorage`.
- **Doc-quality regression tests** (12 new, total suite 1054):
  `mkdocs build --strict` succeeds, every internal link
  resolves, every existing `docs/*.md` is reachable from the
  nav OR redirect-mapped, every redirect target points at a
  real file, the landing page links to QUICKSTART + embeds the
  install one-liner.
- **Source docstring polish** surfaced by the auto-doc:
  `tool_sources.py` and `toolchain_registry.py` `Raises:`
  blocks reformatted to the Google-style `Error: description`
  shape griffe expects.  Pure docstring edits; no behaviour
  change.

## [0.5.0] — 2026-05-03

The toolchain-management track lands.  Two waves ship together:
Wave 3 (`add-onboarding-wizard`) welds the Wave-2 installer into
five user-facing entry points; Wave 4 (`add-recovery-tools`) adds
the daily hardware-bring-up verbs (`alloy reset` / `erase` /
`monitor`).

### Added — Wave-4 of toolchain-management

- **`add-recovery-tools`** — Wave 4 closes the user-facing arc by
  giving the firmware developer the three primitives every embedded
  engineer reaches for during normal hardware bring-up: `alloy
  reset`, `alloy erase`, `alloy monitor`.  All three dispatch
  through one shared orchestrator (`core.probe_orchestrator`) that
  owns probe selection, binary resolution from `.alloy/toolchain.
  lock`, and the typed-error vocabulary.  The CLI, the TUI
  `MonitorScreen`, and six MCP tools all route through that one
  seam.
- **`alloy reset`** — non-destructive CPU / nRST reset.  `--soft`
  (default) issues a CPU reset via probe-rs's `reset` verb; `--hard`
  pulses nRST via `--connect-under-reset`; `--halt-after-reset`
  leaves the core halted post-reset for debugger attach;
  `--probe vid:pid:serial` matches `alloy flash`'s selector
  semantics.
- **`alloy erase`** — flash erase with two safety gates.  TTY prompt
  (default N) renders the plan + chip id + total bytes before
  asking `Continue?`; `--auto` / `--yes` bypasses in non-TTY
  contexts.  `--region NAME|0xBASE-0xEND` (repeatable) for partial
  erase; literal ranges pass through, named aliases resolve via
  the device IR (Wave-5 will wire the bridge — current behaviour:
  raises `family-toolchain-erase-unsupported-region`).
- **`alloy monitor`** — live UART / RTT log viewer.  Replaces the
  `screen /dev/cu.usbmodem*` workflow.  `--port` always required
  (USB enumeration is host-specific); `--baud` autodetected from
  `alloy.toml`'s console UART or falls back to 115200; `--mode raw`
  / `rtt`; `--ansi/--no-ansi` toggles escape-sequence pass-through.
  Press `Ctrl+]` to disconnect — exit 0 + one-line summary
  (`<bytes> bytes captured over <secs>s`).
- **New `core.probe_orchestrator` module** (UI-free) — frozen+slots
  dataclasses (`ProbeIdentity`, `ResetReport`, `EraseRegion`,
  `ErasePlan`, `EraseReport`), sealed `MonitorEvent` union
  (`MonitorOpened` / `MonitorBytes` / `MonitorClosed`), `Probe`
  Protocol, `FakeProbe` test seam, `_RealProbeRsProbe` subprocess
  backend, `MonitorSessionTable` for the MCP session-style monitor.
  Public functions: `select_probe`, `reset_target`, `plan_erase`,
  `execute_erase`, `open_monitor`, `real_probe_for`.  AST-based
  contract test enforces UI-free invariant.
- **TUI `MonitorScreen`** — Textual `RichLog` viewer registered via
  `register_screen("monitor", …)`.  Worker thread runs the
  orchestrator; events stream back via `app.call_from_thread`
  mirroring the Wave-3 OnboardingScreen pattern.  Dismisses with a
  typed `MonitorSummary` on Ctrl+] / Esc.
- **Six new MCP tools**: `probe_reset` (idempotent + safe);
  `probe_erase_plan` (read-only preview); `probe_erase` (mutating;
  refuses without `confirm=true`, mirroring Wave-3's two-phase
  pattern); `probe_monitor_open` / `probe_monitor_poll` /
  `probe_monitor_close` (session-style; UUIDs auto-close after 5
  minutes idle so crashed agents never leak threads).
- **Nine new typed `error_type` strings** registered in the
  uniqueness guard:
  `family-toolchain-probe-{not-found,not-attached,
  multiple-attached,unauthorised}`,
  `family-toolchain-erase-{aborted,unsupported-region,
  confirmation-required,probe-failed}`, and
  `probe-operation-cancelled`.  Cookbook anchors for every entry.
- **Vendor-probe contract**: vendor-only probes (proprietary
  J-Link, locked ST-Link) raise
  `family-toolchain-probe-unauthorised` with `vendor_tool` +
  `install_doc_url` populated.  The orchestrator NEVER auto-invokes
  vendor utilities.  Conservative default heuristic
  (`ALLOY_PROBE_VENDOR_ONLY=<vid:pid>` opts a specific probe in).
- **New `docs/RECOVERY.md`** (the contributor reference): three
  commands + decision matrix + orchestrator API + `Probe` Protocol
  contract + two-phase MCP pattern + vendor-probe contract +
  cancellation contract + cross-links to Waves 1-3 docs.
  `docs/QUICKSTART.md` addendum points at it.  System prompt
  documents the canonical workflow + the `confirm=true` safety
  gate.
- **112 new tests** cover the orchestrator (27), the entry-point
  contract (4), `alloy reset` (9), `alloy erase` (10),
  `alloy monitor` (10), TUI `MonitorScreen` (7), MCP probe tools
  (18), doc regression guards (14), error-type uniqueness guards
  (13).  Total suite: 1042 passing.

### Added — Wave-3 of toolchain-management

- **`add-onboarding-wizard`** — Wave 2's installer is now welded
  into the user-facing flows.  A new contributor goes from
  `pip install alloy-cli` to a flashed Nucleo without leaving
  alloy-cli.  All five surfaces (alloy new, alloy doctor --fix,
  alloy setup, the TUI Onboarding screen, the MCP write tool)
  dispatch through one shared walker
  (`core.toolchain_orchestrator.install_family`) — single source
  of truth for tier walk + vendor short-circuit + lockfile update.
- **`alloy new --install-toolchain` post-scaffold prompt** —
  default Y in a TTY, default N otherwise.  Tri-state via
  `--install-toolchain` / `--no-install-toolchain` / (implicit).
  `--auto` suppresses the confirmation.  The plan renders before
  the prompt; the next-step panel always names
  `alloy toolchain install` when the install was skipped.
- **`alloy doctor --fix` toolchain auto-installer** — extends the
  existing fixer queue with a synthetic `toolchain:<tool>` row
  per missing required non-vendor tool.  `--with-recommended`
  extends the queue to the recommended tier.  Vendor tools stay
  info-severity (never auto-fetched).  Per-tool failures do NOT
  abort the queue.
- **New `alloy setup` standalone command** — guided wizard for a
  fresh machine.  Detects project state, embeds `alloy new` when
  no project exists, dispatches the install through the shared
  orchestrator.  `--board`, `--family`, `--auto`, `--no-tui`,
  `--project-dir`.  SIGINT mid-install → exit 130 with partial
  outcomes summarised.
- **TUI `OnboardingScreen` 3-phase wizard** (replaces the Wave-1
  placeholder) — family picker → plan review → live progress.
  Vendor rows render dim with the install_doc URL inline.  Worker
  thread runs the orchestrator; events stream back via
  `app.call_from_thread`.  Cancellation raises
  `OnboardingCancelledError` with partial outcomes.
- **New MCP write-side tool `alloy.toolchain_apply_install_plan`**
  — the mutating complement to Wave 2's
  `toolchain_install_plan`.  Two-phase pattern: agents preview
  first, get explicit confirmation, then apply.  Idempotent
  (re-run on a fully-installed family returns every row with
  `skipped=true, reason="already-installed"`, zero bytes).
  Vendor surfaces with `reason="vendor"` + `install_doc_url`.
  Per-tool typed errors propagate via the standard envelope.
- **New `OnboardingCancelledError`** (`error_type="onboarding-
  cancelled"`) — carries `partial_outcomes` so callers can
  summarise what already installed before the abort.  CLI
  surfaces map it to exit code 130.
- **New `core.toolchain_orchestrator.plan_install` /
  `install_family`** — public API; UI-free (no Click / Rich /
  Textual / `input()` / `sys.stdin`).  AST-checked invariant.
- **New `commands/_install_view.py`** — shared Rich rendering
  (`render_install_plan`, `render_install_summary`,
  `make_event_logger`, `human_bytes`) reused across `alloy new`,
  `alloy setup`, future `alloy doctor --fix` + `alloy toolchain
  install` refactors.
- **Documentation**: new `docs/TOOLCHAIN_ONBOARDING.md` (the
  contributor reference: decision matrix, orchestrator API,
  InstallEvent contract, two-phase MCP pattern, vendor contract,
  cancellation contract, code locations); rewritten
  `docs/QUICKSTART.md` (the "5 minutes to first ELF" walkthrough
  now uses the post-scaffold install prompt); cookbook anchor for
  `onboarding-cancelled`.
- **121 new tests** cover the orchestrator (15), the entry-point
  contract (5), `alloy new` integration (16), `alloy doctor --fix`
  (15), `alloy setup` (10), TUI onboarding (5), MCP apply tool
  (8), doc regression guards (14), and error-type uniqueness
  guards (6).  Total suite: 936 passing.

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
