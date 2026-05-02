# Add the DoctorScreen TUI + Auto-Fix

## Why

`add-doctor-update-export` (#15) shipped the CLI side of `alloy
doctor` but deferred the TUI screen described in
`docs/TUI_DESIGN.md` Screen 11.  Today users hit the same data
through a Rich table; that's fine for a glance, but the spec
called for a live screen with `r` re-run + `f` auto-fix bindings
plus interactive remediation for safe issues (pip-install missing
deps, init the alloy-devices-yml submodule).

Without that screen, the dashboard shows toolchain pills in the
top bar but never lets the user actually fix what's broken from
inside the TUI — they have to drop to the shell.

## What Changes

### `tui.screens.DoctorScreen`

- Mounts a `DataTable` populated from
  `core.diagnose.run().checks`.
- Per-row columns: glyph + name + severity + message + hint +
  auto-fix availability.
- Bindings:
  - `r` re-run the report (call `core.diagnose.run` again,
    refresh the table).
  - `f` apply the auto-fix on the highlighted row.
  - `Enter` shows the full check detail (install hint, auto-fix
    command preview, last-run timestamp) in a side panel.
  - `Esc` closes.

### Auto-fix execution

- `core.diagnose.AutoFix` typed callable: takes a
  `CheckResult`, returns an `AutoFixOutcome { ok, log }`.
- Two built-in fixes ship today:
  - `pip-install-mcp-extras` for the `mcp` Python optional dep
    when the user wants the official SDK.
  - `init-alloy-devices-submodule` runs `git submodule update
    --init` in the repo root.
- Auto-fixers run via `core.process.runner` so tests and the TUI
  share the same subprocess seam.
- Diagnostics whose `auto_fix` field is `None` keep `f` disabled
  for that row.

### CLI auto-fix mode

- `alloy doctor --fix` runs every available auto-fix, prints a
  summary, exits 0 only when every error-severity row passes.

### Dashboard hook

- The dashboard's existing toolchain row gains a footer hint:
  *"Press d to open Doctor"*.  The `d` binding on Dashboard now
  routes to `DoctorScreen` instead of the polite no-op
  notification it shows today.

## Impact

The TUI gains a complete status-and-remediate loop without
leaving the terminal.  CI gains `alloy doctor --fix` for
"please make this machine bootable" jobs (e.g., container
warm-ups).

## What this DOES NOT do

- Does not auto-install system toolchains (arm-gcc, probe-rs,
  cmake).  The screen prints the install command, never runs it.
- Does not introduce a sandbox / approval flow — auto-fixes the
  user invokes via `f` execute immediately.  The intent is
  "small, safe, idempotent".
- Does not replace the existing Rich-table CLI output; the new
  TUI is the interactive companion.
