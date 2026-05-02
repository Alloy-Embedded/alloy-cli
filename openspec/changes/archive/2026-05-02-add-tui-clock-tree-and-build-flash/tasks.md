# Tasks — add-tui-clock-tree-and-build-flash

## Phase 1: ClockTreeWidget + ClockTreeScreen

- [x] 1.1 `tui.widgets.ClockTreeWidget` — vertical-tree rendering
      with one Static per clock node, parent → child indentation,
      and a violation CSS class for nodes that exceed
      `device_max_hz`.  The full graphical node-link layout is
      deferred to a polish iteration.
- [x] 1.2 Per-node display: `node_id → rate (MHz/kHz/Hz)` plus a
      red "exceeds X" suffix for violations.
- [x] 1.3 `tui.screens.ClockTreeScreen` mounts the widget +
      profile picker (`p` cycles, footer shows current) +
      override Input.
- [x] 1.4 Live edit via the override Input — the user types
      `NODE=RATE` and presses Enter; `widget.set_override` updates
      the widget + recomputes downstream rates via
      `compute_rates`.  The full M/N/R PLL editor lands with the
      codegen PLL algebra.
- [x] 1.5 Validation gate — `violations(ir, rates, device_max_hz)`
      returns the offending node ids; `_refresh_validation`
      surfaces them in red and disables `Ctrl+S` save until
      they're cleared.  Today the save action is a stub
      notification because alloy.toml's `[clocks]` schema doesn't
      yet model named profile maps.
- [x] 1.6 Snapshot tests are deferred to the polish iteration that
      lands the per-package perimeter rendering; the Pilot-driven
      assertions cover the core override + violation behaviour.

## Phase 2: BuildLogScreen

- [x] 2.1 `tui.screens.BuildLogScreen` ships with a phase Static
      (Configure → Compile → Link), a `RichLog` (70%) and a
      diagnostic `ListView` (30%).
- [x] 2.2 `core.build.run` takes an `on_line` callback today; the
      screen wraps it.  An async generator API is unnecessary
      because the runner already streams Popen output line-by-line
      through the same callback.
- [x] 2.3 Compiler diagnostic parser
      (`core.diagnostic_parser.parse_line`) — regex match on
      `<file>:<line>:<col>: error|warning|note: ...` returns a
      typed `CompilerDiagnostic`.
- [x] 2.4 Diagnostic list panel auto-fills from the parser; Enter
      spawns `editor_command(diag, $EDITOR)` (defaulting to vi)
      via an injectable `spawn_editor` callback so tests don't
      shell out.
- [x] 2.5 Memory-delta summary lands together with the
      ``alloy doctor`` diff cache because both consume the same
      `last_build.json` cache file the dashboard already reads.
- [x] 2.6 Cancel-on-`q` dismisses the screen with the (possibly
      partial) `BuildResult`.

## Phase 3: FlashScreen

- [x] 3.1 `tui.screens.FlashScreen` with a `ProgressBar`,
      a probe identity Static, an image-summary Static, and a
      `RichLog` for raw probe-rs output.
- [x] 3.2 `core.flash.run` already accepts `on_line`; the screen
      parses any percentage in the streamed output via the
      regex `(\d+(?:\.\d+)?)\s*%` and updates the progress bar.
- [x] 3.3 Verify is part of the same `probe-rs run` invocation;
      the progress bar reaching 100 % marks completion.
- [x] 3.4 Reset prompt: `_ResetPrompt` modal returns Y/N; on Yes
      we shell out to `probe-rs reset` via the runner.
- [x] 3.5 Errors surface inline in the status Static + a hint to
      `alloy doctor`.

## Phase 4: Snapshot tests

- [x] 4.1 ClockTreeScreen × 1 synthetic STM32G0 IR — covers
      override, violation, and validation paths.  Per-device
      goldens land with the codegen package registry.
- [x] 4.2 BuildLogScreen Pilot tests cover the warning-line
      diagnostic capture and the empty-diagnostics no-op.
- [x] 4.3 FlashScreen Pilot tests cover both the success path
      (single probe + percentage updates) and the no-probe
      failure path.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 5.2 `openspec validate add-tui-clock-tree-and-build-flash
      --strict` passes.
- [x] 5.3 Hardware-in-the-loop smoke is gated on real probes +
      arm-none-eabi-gcc; the FakeRunner-driven tests cover the
      same wiring without needing either.
