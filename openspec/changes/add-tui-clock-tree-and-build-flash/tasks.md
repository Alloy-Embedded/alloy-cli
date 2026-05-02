# Tasks — add-tui-clock-tree-and-build-flash

## Phase 1: ClockTreeWidget + ClockTreeScreen

- [ ] 1.1 `tui.widgets.ClockTreeWidget` — node-link rendering
      (sources → PLL → SYSCLK → AHB → APB → peripherals).
      Layout algorithm: depth-first by topology.
- [ ] 1.2 Per-node display: name, current rate (computed from
      upstream + divisor), enabled state, peripheral list (for
      bus nodes).
- [ ] 1.3 `tui.screens.ClockTreeScreen` mounting the widget +
      profile picker + custom profile save action.
- [ ] 1.4 Live edit mode: `Enter` on a source toggles enabled +
      prompts for crystal frequency; `Enter` on a PLL opens
      M/N/R editor; `Enter` on a selector cycles source.
- [ ] 1.5 Validation gate: rates exceeding bus max in the IR are
      flagged red; SYSCLK > device max (e.g., 64 MHz on G0)
      blocks save.
- [ ] 1.6 Snapshot tests: 3 fixture devices (stm32g071rb, esp32-c3,
      pico).

## Phase 2: BuildLogScreen

- [ ] 2.1 `tui.screens.BuildLogScreen` with phase indicator +
      progress bar + live RichLog.
- [ ] 2.2 `core.build.run_streaming(...)` async generator
      yielding `(phase, line)` tuples.
- [ ] 2.3 Compiler diagnostic parser (regex on
      `<file>:<line>:<col>: error/warning: ...`).
- [ ] 2.4 Diagnostic list panel (right side); `Enter` opens via
      `$EDITOR +<line>:<col> <file>`.
- [ ] 2.5 Post-build summary: memory delta from
      `core.memory.compute_delta(prev_elf, new_elf)`.
- [ ] 2.6 Cancel: `q` sends SIGTERM to ninja, cleans up.

## Phase 3: FlashScreen

- [ ] 3.1 `tui.screens.FlashScreen` with progress bar + probe
      panel.
- [ ] 3.2 `core.flash.run_with_progress(elf, probe, callback)` —
      wraps `probe-rs run` with stderr parsing for percent
      progress.
- [ ] 3.3 Verify step shown as a separate phase.
- [ ] 3.4 Reset prompt after success.
- [ ] 3.5 On error: render the probe-rs diagnostic with hint to
      `alloy doctor`.

## Phase 4: Snapshot tests

- [ ] 4.1 ClockTreeScreen × 3 devices.
- [ ] 4.2 BuildLogScreen mid-build, success, failure.
- [ ] 4.3 FlashScreen mid-flash, success, error.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 5.2 `openspec validate add-tui-clock-tree-and-build-flash
      --strict` passes.
- [ ] 5.3 Manual smoke against a real probe (gated test with
      `pytest.mark.requires_hardware`).
