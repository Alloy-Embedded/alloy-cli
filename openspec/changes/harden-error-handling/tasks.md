# Tasks — harden-error-handling

## Phase 1: Logging seam

- [ ] 1.1 `core.log.get_logger(name)` returns a stdlib
      `logging.Logger` whose handler appends to
      `.alloy/cache/alloy-cli.log`.
- [ ] 1.2 Rotation: one rolling backup once the file passes
      1MB (`logging.handlers.RotatingFileHandler`).
- [ ] 1.3 The log path is overridable via the
      `ALLOY_CLI_LOG` environment variable so tests can pin
      it to a tmp path.

## Phase 2: Audit + reclassify the 10 bare catches

- [ ] 2.1 `core.diagnose._project_check` — narrow to
      `(ProjectConfigError, FileNotFoundError, OSError)`.
- [ ] 2.2 `core.flash._read_probes_json` — narrow to
      `(json.JSONDecodeError, OSError)`; log via the new
      logger.
- [ ] 2.3 `core.codegen._discover_entry` /
      `core.codegen._read_stamp` — narrow to
      `(ImportError, ModuleNotFoundError, OSError, json.
      JSONDecodeError)`.
- [ ] 2.4 `tui.app._on_unhandled_action` — keep broad catch
      but route through logger + notify; document why
      Textual's binding seam needs it.
- [ ] 2.5 `tui.screens.dashboard.__init__` — narrow to
      `ProjectConfigError`; surface via existing inline error.
- [ ] 2.6 `tui.screens.onboarding._submit_step_*` — narrow per
      step (json / config / OS errors).
- [ ] 2.7 `tui.screens.clock_tree._on_save_diff_applied` —
      narrow to `ProjectConfigError`.
- [ ] 2.8 `tui.screens.peripheral_add._resolve_device_for` /
      `_load_context` — narrow to
      `(DeviceNotFoundError, BoardNotFoundError,
      ProjectConfigError)` and rethrow as
      `AlloyCliError` with a structured diagnostic.

## Phase 3: Façade error contract

- [ ] 3.1 `commands.<everything>` — top-level Click handler
      maps `AlloyCliError.error_type` to a stable exit code
      table; the table is documented in `core.errors`.
- [ ] 3.2 `tui.app` global error hook surfaces every
      `AlloyCliError` via `notify(severity="error")` plus a
      log line.
- [ ] 3.3 `mcp.tools.ToolRegistry.call` already wraps
      `AlloyCliError` → `ToolError`; we audit that the new
      narrowed catches still hit it.

## Phase 4: Tests

- [ ] 4.1 Each narrowed catch has a unit test that triggers
      the predictable failure and asserts the resulting
      `AlloyCliError` subclass + message.
- [ ] 4.2 Pilot tests assert `notify(severity="error")` fires
      with the typed message on the dashboard /
      peripheral-add / clock-tree screens.
- [ ] 4.3 `tests/test_log.py` covers log rotation + the
      `ALLOY_CLI_LOG` override.
- [ ] 4.4 ruff `BLE001` re-enabled; the suite passes with no
      `# noqa: BLE001` markers in `src/`.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [ ] 5.2 `openspec validate harden-error-handling --strict`
      passes.
