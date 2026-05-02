# Add TUI Clock Tree, Build Log, and Flash Progress Screens

## Why

Three Phase-3 screens that complete the TUI's daily-driver loop.
See `docs/TUI_DESIGN.md` Screens 4 (Clock Tree), 7 (Build Log),
8 (Flash Progress).  We bundle them in one proposal because they
share the same underlying live-streaming infrastructure and ship
together as the "build/flash UX" wave.

## What Changes

### `tui.screens.ClockTreeScreen`

- Renders `device.clock_nodes` + `clock_selectors` + `clock_gates`
  as a navigable node-link diagram via the new
  `tui.widgets.ClockTreeWidget`.
- Live-edit: pressing `Enter` on a source / PLL / selector opens
  an inline editor that updates rates in real time.
- Profile picker: `p` cycles between predefined profiles; `n`
  saves current state as a new profile in `alloy.toml [clocks]`.
- Per-peripheral clock annotations: shows which peripherals each
  PCLK / HCLK feeds, with ✓/◈ markers for "configured / orphan".
- Validation: flags rates exceeding bus maxima from the IR.

### `tui.screens.BuildLogScreen`

- Live-streamed output of `core.build.run(...)` via Textual
  `RichLog`.
- Phase indicator (Configure → Codegen → Compile → Link →
  Post-process) with progress bar.
- Compiler diagnostics parsed into a navigable list — `Enter` on
  an error opens it in `$EDITOR`.
- After completion: memory delta vs previous build (flash + RAM
  bytes change).

### `tui.screens.FlashScreen`

- Live progress bar driven by `core.flash.run_with_progress`.
- Probe identification panel (vendor / serial / firmware version).
- Image preview: ELF size, target address, computed CRC.
- After flash: prompt "reset target?" with default `Y`.

## Impact

After this proposal, the `alloy ui` flow is complete: pick board
→ configure → build (live) → flash (live) → debug.  No external
tool invocation surfaces in the user's terminal.

## What this DOES NOT do

- DMA Matrix screen (Phase 5 — `add-doctor-update-export`).
- Memory Map screen (Phase 5).
- Custom GDB UI — we just spawn the configured external GDB.
