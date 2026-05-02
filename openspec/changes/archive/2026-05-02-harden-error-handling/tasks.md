# Tasks — harden-error-handling

## Phase 1: Logging seam

- [x] 1.1 `core.log.get_logger(name)` returns a stdlib
      `logging.Logger` whose handler appends to
      `.alloy/cache/alloy-cli.log`.
- [x] 1.2 `RotatingFileHandler` with `maxBytes=1_048_576` +
      `backupCount=1` matches the spec rotation contract.
- [x] 1.3 The log path is overridable via the
      `ALLOY_CLI_LOG` environment variable; `core.log.reset_for_tests`
      clears the per-process cache so tests can rebind.

## Phase 2: Audit + reclassify the bare catches

- [x] 2.1 `core.diagnose._project_check` — narrowed to
      `(ProjectConfigError, OSError)`.
- [x] 2.2 `core.flash._target_for` — narrowed to
      `BoardNotFoundError`.
- [x] 2.3 `core.codegen._discover_entry` — narrowed to
      `(ImportError, ModuleNotFoundError)`.
- [x] 2.4 `core.codegen._run_entry` — kept broad with
      `# noqa: BLE001` (third-party callable; logged via the
      module logger).
- [x] 2.5 `tui.app._on_palette_dismissed` — kept broad with
      `# noqa: BLE001` (user-registered factory; logged via
      `core.log`).
- [x] 2.6 `tui.screens.dashboard.__init__` — narrowed to
      `(ProjectConfigError, OSError)`.
- [x] 2.7 `tui.screens.flash._launch_flash` /
      `_on_reset_response` — narrowed to `(AlloyCliError,
      OSError)` and `OSError` respectively.
- [x] 2.8 `tui.screens.build_log._launch_build` — narrowed to
      `(AlloyCliError, OSError)`.
- [x] 2.9 `tui.screens.clock_tree._on_save_diff_applied` —
      narrowed to `(ProjectConfigError, OSError)`.
- [x] 2.10 `tui.screens.peripheral_add` — three sites:
       `on_mount` → `(ProjectConfigError, OSError)`;
       `_refresh` → `(AlloyCliError, KeyError, TypeError)`;
       `_resolve_device_for` → `(BoardNotFoundError,
       DeviceNotFoundError, DataRepoMissingError)`.
- [x] 2.11 `tui.screens.onboarding._capture_step` →
       `ValueError`; `_apply_scaffold` →
       `(AlloyCliError, OSError)`.
- [x] 2.12 `mcp.server._try_import_mcp` → `(ImportError,
       ModuleNotFoundError)`.
- [x] 2.13 `commands.debug._target_for` → `BoardNotFoundError`.

## Phase 3: Façade error contract

- [x] 3.1 The Click runner already converts
      `AlloyCliError`s — every narrowed catch now rethrows or
      surfaces an inline diagnostic so the typed contract
      holds.
- [x] 3.2 The Textual app's command-palette dispatcher logs
      via `core.log` and notifies on `severity="error"`.
- [x] 3.3 MCP `ToolRegistry.call` already wraps
      `AlloyCliError → ToolError`; the audited catches still
      hit it.

## Phase 4: Tests

- [x] 4.1 `tests/test_log.py` covers
      `get_logger` round-trip, per-name caching,
      `reset_for_tests`, and the stderr fallback when the log
      file path can't be created.
- [x] 4.2 `tests/test_error_handling_narrowing.py` walks the
      AST of every module under `src/alloy_cli/` and asserts
      the bare-catch count matches a tiny allow-list.  A new
      offender fails CI.
- [x] 4.3 ruff `BLE001` re-enabled in
      `pyproject.toml [tool.ruff.lint].select`; the suite
      passes with only the 2 documented `# noqa: BLE001`
      markers (codegen + app palette).

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [x] 5.2 `openspec validate harden-error-handling --strict`
      passes.
