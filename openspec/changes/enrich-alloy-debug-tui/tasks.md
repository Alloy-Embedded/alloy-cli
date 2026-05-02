# Tasks — enrich-alloy-debug-tui

## Phase 1: GDB adapter

- [ ] 1.1 `core.gdb.GdbSession` dataclass + lifecycle
      methods (`__enter__` / `__exit__` tear down the
      subprocess cleanly).
- [ ] 1.2 MI2 wire parser: `parse_mi2(line) -> MiRecord` for
      result records, async records, console streams.
- [ ] 1.3 Typed responses: `StopReason`, `Frame`,
      `Variable`, `Register`, `MemorySlice`.
- [ ] 1.4 Methods: `connect_target`, `load`,
      `set_breakpoint`, `delete_breakpoint`, `continue_`,
      `step`, `next`, `finish`, `interrupt`, `eval`,
      `read_memory`, `disassemble`.
- [ ] 1.5 `core.gdb.start_gdb_server(runner, target, port)`
      spawns `probe-rs gdb-server` and returns a context
      manager that kills the process on exit.

## Phase 2: DebugScreen

- [ ] 2.1 `tui.screens.DebugScreen` with the 2×3 panel grid.
- [ ] 2.2 Source panel: `Syntax`-based view with breakpoint
      gutter + PC arrow.
- [ ] 2.3 Call stack: `DataTable` populated from `-stack-
      list-frames`; `Enter` jumps Source.
- [ ] 2.4 Locals + watches: `Tree` populated from `-stack-
      list-variables` and the user's watch expressions.
- [ ] 2.5 Registers: `DataTable` populated from
      `-data-list-register-values`.
- [ ] 2.6 GDB log: `RichLog` mirroring every MI2 command +
      response.
- [ ] 2.7 Bindings: c, s, n, o, b, i, w, Esc.

## Phase 3: CLI integration

- [ ] 3.1 `alloy debug --tui` (default on a TTY) launches
      `DebugScreen`; `--no-tui` keeps the wrapper.
- [ ] 3.2 `--port N` overrides the gdb-server port.
- [ ] 3.3 Probe selection auto-detects via
      `core.flash.detect_probes`; multi-probe disambiguation
      via interactive picker.

## Phase 4: Crash recovery

- [ ] 4.1 SIGCHLD handler tears the session down on
      gdb-server exit.
- [ ] 4.2 The screen surfaces a typed error notification +
      logs to `.alloy/cache/alloy-cli.log`.
- [ ] 4.3 No orphan PIDs after the screen dismisses.

## Phase 5: Tests

- [ ] 5.1 Unit tests for `parse_mi2` against canned output
      (load / breakpoint set / continue / hit-breakpoint /
      step / interrupt / eval / read-memory).
- [ ] 5.2 Pilot tests: DebugScreen with a `FakeRunner` that
      replays a canned MI2 transcript; assert each panel
      reflects the expected state.
- [ ] 5.3 `alloy debug --tui --no-launch` (test-only flag)
      mounts the screen against a fake session for the
      Pilot.
- [ ] 5.4 `tests/test_gdb_session_lifecycle.py` confirms
      that an early exit of the gdb-server process tears
      down the screen without orphan PIDs.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/cli-surface/spec.md` and
      `specs/tui-experience/spec.md`.
- [ ] 6.2 `openspec validate enrich-alloy-debug-tui
      --strict` passes.
- [ ] 6.3 `docs/TUI_DESIGN.md` Screen 13 section added in a
      follow-up doc-only PR — the spec already pins the
      contract.
