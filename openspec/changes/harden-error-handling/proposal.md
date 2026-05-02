# Replace Bare `except Exception` with Structured Diagnostics

## Why

The repo carries 10 `except Exception:` (or similar bare-catch)
sites across `core/diagnose`, `core/flash`, `core/codegen`,
`tui/app`, `tui/screens/{dashboard,onboarding,clock_tree,
peripheral_add}`.  These swallow real errors with a `# noqa:
BLE001` and either log nothing or print a generic
notification.

The product surface promises *typed* errors:
`AlloyCliError` is the public contract every façade renders
(CLI exit code, TUI toast, MCP `error_type` payload).  Bare
catches break that contract — when something explodes, the
user gets "something went wrong" instead of "alloy-devices-yml
submodule is uninitialised, run `git submodule update --init`."

## What Changes

### Audit + reclassify

- Each bare-catch site is reviewed and mapped onto one of
  three outcomes:
  1. *Predictable failure* (file not found, JSON parse,
     subprocess error) — narrow the catch to the specific
     exception and rethrow as the matching
     `AlloyCliError` subclass.
  2. *Inherent third-party noise* (Textual binding rewires,
     library imports, Rich render quirks) — keep the catch
     but log via `core.log` (added in this proposal) so the
     suppression is auditable.
  3. *Programmer error* (would indicate a bug) — drop the
     catch entirely, let the test suite surface the crash.

### Structured logging seam

- New `core.log.get_logger(name) -> logging.Logger` returns a
  module logger configured to write to
  `.alloy/cache/alloy-cli.log` (append, capped to 1MB with one
  rolling backup).
- Replaces every bare `print(...)` warning in the audited
  paths.

### Façade contract

- CLI catches every `AlloyCliError` at the top level and exits
  with a stable `error_type → exit_code` table; today this is
  ad-hoc.
- TUI catches `AlloyCliError` per-action and emits a
  `notify(severity="error")` with the typed message.
- MCP wraps `AlloyCliError` into a `ToolError(error_type=…,
  message=…)` payload (already partially the case; we close
  the remaining gaps).

## Impact

- Errors that today surface as a generic notification become
  actionable rows with install hints / next-step commands.
- The log file under `.alloy/cache/` becomes the canonical
  place to grep when something misbehaves.
- ruff's `BLE001` rule is re-enabled (we currently have
  `# noqa` markers on three modules).

## What this DOES NOT do

- Does not introduce a new exception hierarchy beyond
  `AlloyCliError` — we map onto the existing subclasses.
- Does not change MCP / CLI exit codes from their current
  values; just makes the mapping explicit.
- Does not introduce structured event emission (that's
  `add-event-log-writer`); the log file is line-text only.
