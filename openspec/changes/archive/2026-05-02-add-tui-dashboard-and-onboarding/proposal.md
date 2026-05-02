# Add TUI Dashboard + Onboarding Wizard

## Why

Two screens that bookend the user journey: **onboarding** is the
first run, **dashboard** is every subsequent run.  Both are
information-dense status views over `alloy.toml`, build state, and
the device IR.  See `docs/TUI_DESIGN.md` Screens 1 and 12.

## What Changes

### Dashboard (`tui.screens.DashboardScreen`)

- Trigger: `alloy` (no args, inside a project) or `alloy ui`.
- Top bar: board / chip identity, toolchain ✓/✗, probe ✓/✗,
  current clock profile, alloy versions.
- Peripherals panel: one row per `[[peripherals]]` entry with
  status glyph, kind, name, key params, pins, DMA.
- Build panel: time of last build, status, errors / warnings,
  flash size.
- Memory mini-bar: flash + RAM usage relative to total.
- Recent activity log: tail of `.alloy/cache/events.jsonl`.
- Hotkeys: `b` build, `f` flash, `d` debug, `a` add, `c` clocks,
  `m` memory, `Ctrl+P` palette.

### Onboarding wizard (`tui.screens.OnboardingScreen`)

- Trigger: `alloy new` without `--board` / `--device`, or `alloy
  ui` outside a project.
- Multi-step flow: name → board picker → clock profile → starter
  peripheral → confirm diff → build?
- Each step has a "skip" option; partial state is persistable.

## Impact

A user new to alloy goes from zero to running firmware via two
keypresses.  An experienced user opens `alloy` to see project
status at a glance.

## What this DOES NOT do

- The Board Picker screen itself is `add-tui-board-picker`; this
  proposal embeds it as a step.
- The Peripheral Add screen is `add-tui-peripheral-assignment`;
  embedded similarly.
- Memory map detail view (Phase 5) — this only ships the mini-bar.
