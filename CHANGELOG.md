# Changelog

All notable changes to **alloy-cli** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Unreleased work lives at the top of the file; releases are tagged
``vX.Y.Z`` and published via ``.github/workflows/release.yml``.

## [Unreleased]

Nothing here yet.

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
