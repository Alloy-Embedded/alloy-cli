# Tasks — add-tui-dashboard-and-onboarding

## Phase 1: Dashboard

- [ ] 1.1 `tui.screens.DashboardScreen` layout per
      `docs/TUI_DESIGN.md` Screen 1.
- [ ] 1.2 Data wiring: top bar from project + IR; peripherals
      panel from `alloy.toml`; build panel from
      `.alloy/cache/last_build.json`; memory bars from last `.elf`;
      activity from `.alloy/cache/events.jsonl`.
- [ ] 1.3 Hotkey routing: `b` → BuildLogScreen, `f` →
      FlashScreen, `d` → debug subprocess, `a` → peripheral picker
      sub-menu, `c` → ClockTreeScreen, `m` → MemoryMapScreen.
- [ ] 1.4 Empty-state messages for projects without peripherals /
      builds.
- [ ] 1.5 Snapshot tests: 3 fixture projects (fresh,
      partially-configured, fully-configured + built).

## Phase 2: Onboarding wizard

- [ ] 2.1 `tui.screens.OnboardingScreen` with step counter.
- [ ] 2.2 Step 1: name input (validates as project name).
- [ ] 2.3 Step 2: embed BoardPickerScreen (from
      `add-tui-board-picker`).  Until that lands, fall back to a
      RichLog of `alloy boards --json`.
- [ ] 2.4 Step 3: clock profile picker — list profiles from chosen
      board's `clock_profiles[]`; default to the board's
      recommended profile.
- [ ] 2.5 Step 4: optional starter peripheral picker — embed
      PeripheralAddScreen later.  Until then: skip.
- [ ] 2.6 Step 5: full diff preview via DiffModal.
- [ ] 2.7 Step 6: optional immediate build (transitions to
      BuildLogScreen).

## Phase 3: Spec + final checks

- [ ] 3.1 Spec deltas in `specs/tui-experience/spec.md`.
- [ ] 3.2 `openspec validate add-tui-dashboard-and-onboarding
      --strict` passes.
- [ ] 3.3 Snapshot tests cover both screens at default + 80×24
      sizes.
