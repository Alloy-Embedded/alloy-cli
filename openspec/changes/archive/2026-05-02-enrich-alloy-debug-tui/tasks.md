# Tasks — enrich-alloy-debug-tui

## Phase 1: GDB adapter

- [x] 1.1 `core.gdb.GdbSession` dataclass owns a
      `subprocess.Popen` (or test fake) speaking MI2 over
      stdin/stdout; `__enter__` / `__exit__` /
      `close()` clean up cleanly.
- [x] 1.2 `parse_mi2(line) -> MiRecord` handles the four
      record kinds (result, async, console, log) plus the
      target-stream variant; unrecognised lines return
      `None`.
- [x] 1.3 Typed responses: `MiRecord`, `StopReason`,
      `Frame`, `Variable`, `Register`, `MemorySlice` (the
      latter four are placeholders for future work; today
      `MiRecord` does the heavy lifting).
- [x] 1.4 High-level methods: `connect_target`, `load`,
      `set_breakpoint`, `delete_breakpoint`, `continue_`,
      `step`, `next`, `finish`, `interrupt`, `eval`.
- [x] 1.5 `core.gdb.launch(...)` spawns the gdb-mi
      subprocess and returns a populated session; the
      banner read is best-effort (drained, never asserted).

## Phase 2: DebugScreen

- [x] 2.1 `tui.screens.debug.DebugScreen` mounts the 5-panel
      layout (Source / Call stack / Locals + watches /
      Registers / GDB log).
- [x] 2.2 Source panel is a `RichLog` placeholder pending the
      Syntax-backed view in a follow-up; gutter / PC arrow
      land then.
- [x] 2.3 Call stack `DataTable` columns: level / func /
      file:line.  Locals panel is a `Tree`; Registers is a
      second `DataTable`.
- [x] 2.4 GDB log mirrors every MI2 record the session has
      seen + every new one the screen issues.
- [x] 2.5 Bindings: c / s / n / o / b / i / w / Esc.

## Phase 3: CLI integration

- [x] 3.1 `alloy debug --tui / --no-tui` (default `--tui` on
      a TTY) flag added.
- [x] 3.2 `--tui` path spawns `core.gdb.launch(...)` against
      the existing probe-rs gdb-server, connects, and pushes
      DebugScreen.
- [x] 3.3 `--no-tui` keeps the wrapper-only behaviour
      (existing flow).
- [x] 3.4 `--gdb-port` / `--port`-equivalent override
      already exists as `--gdb-port`; reused.

## Phase 4: Crash recovery

- [x] 4.1 GdbSession.close() writes `-gdb-exit` then waits;
      timeout / OSError falls back to `process.kill()` so we
      never leave orphan PIDs.
- [x] 4.2 The DebugScreen's `action_cancel` closes the
      session before dismissing.
- [x] 4.3 GdbSessionError is raised on `^error` records; the
      screen surfaces them via `notify(severity="error")`.

## Phase 5: Tests

- [x] 5.1 `tests/test_gdb_session.py` (18 cases): MI2 parser
      across every record kind, GdbSession command
      round-trip, error propagation, lifecycle.
- [x] 5.2 `tests/test_debug_screen.py` (7 cases): all five
      panels mount, every action wires the right MI2
      command, breakpoint round-trip stores then deletes,
      Esc closes the session, GDB log replays prior records.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/cli-surface/spec.md` and
      `specs/tui-experience/spec.md`.
- [x] 6.2 `openspec validate enrich-alloy-debug-tui --strict`
      passes.
- [x] 6.3 Error cookbook gained the `gdb-session-error`
      anchor; cheatsheet picks up the `--tui/--no-tui`
      flags automatically.
