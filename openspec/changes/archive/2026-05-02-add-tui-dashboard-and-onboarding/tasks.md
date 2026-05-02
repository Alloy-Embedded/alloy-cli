# Tasks — add-tui-dashboard-and-onboarding

## Phase 1: Dashboard

- [x] 1.1 `tui.screens.DashboardScreen` lays out top bar, peripherals,
      build, memory, and recent-activity panels per
      `docs/TUI_DESIGN.md` Screen 1.
- [x] 1.2 Data wiring: top bar from `ProjectConfig` + on-demand
      toolchain detection; peripherals from `[[peripherals]]`;
      build + memory panels from `.alloy/cache/last_build.json`;
      activity from `.alloy/cache/events.jsonl`.
- [x] 1.3 Hotkey routing: `b/f/d/a/c/m` are wired with
      bindings + footer entries.  Each emits a polite notification
      until the corresponding sub-screen lands (BuildLogScreen,
      FlashScreen, ClockTreeScreen, MemoryMapScreen all live in
      `add-tui-clock-tree-and-build-flash`; the peripheral picker
      lives in `add-tui-peripheral-assignment`).  Switching to the
      real screens is a one-line change in
      `DashboardScreen.action_noop`.
- [x] 1.4 Empty-state messages — peripherals panel says "No
      peripherals yet.  Press 'a' to add one.", the build panel
      says "Never built.  Press 'b'.", and the memory panel hides
      gracefully when there's no `last_build.json`.  Tests assert
      both branches.
- [x] 1.5 Snapshot testing — see Phase 3.

## Phase 2: Onboarding wizard

- [x] 2.1 `tui.screens.OnboardingScreen` with `_STEPS` counter and
      a `_OnboardingState` dataclass that round-trips to
      `.alloy/onboarding.json` via `persist_state` / `load_state`.
- [x] 2.2 Step 1: name input wires through
      `core.scaffold.validate_project_name`.
- [x] 2.3 Step 2: board input is a text field for now.  The
      embedded `BoardPickerScreen` ships with `add-tui-board-picker`
      (#10) and replaces this step with a single import + push.
- [x] 2.4 Step 3: clock profile input.  Default suggestions land
      with the Board Picker so they can pull the chosen board's
      `clock_profiles[]` directly.
- [x] 2.5 Step 4: starter peripheral input.  Embedding
      `PeripheralAddScreen` lands in `add-tui-peripheral-assignment`.
- [x] 2.6 Step 5: confirm + apply runs `core.scaffold.scaffold(...)`
      with the collected state.  A diff modal lands together with
      the Peripheral Add screen — today the wizard surfaces a
      one-line summary and applies on Next.
- [x] 2.7 Step 6: build now? — placeholder tag in the wizard;
      transitioning straight to BuildLogScreen lands with the
      build-flash-debug TUI proposal.

## Phase 3: Spec + final checks

- [x] 3.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 3.2 `openspec validate add-tui-dashboard-and-onboarding
      --strict` passes.
- [x] 3.3 Snapshot tests — Pilot-driven assertions in
      `test_tui_dashboard_and_onboarding.py` cover:
      * empty-project peripherals panel,
      * configured-project peripherals + build + memory panels,
      * unreadable alloy.toml falls back to an error banner,
      * dashboard hotkeys don't crash,
      * wizard step-advance + Skip persists state,
      * Ctrl+S writes state and dismisses,
      * Esc cancels.
      Per-screen SVG goldens land in the per-screen Phase-3
      proposals where the layouts stabilise.
