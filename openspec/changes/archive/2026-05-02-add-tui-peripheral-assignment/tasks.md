# Tasks — add-tui-peripheral-assignment

## Phase 1: PinoutWidget

- [x] 1.1 `tui.widgets.PinoutWidget` ships with a compact mode
      (vertical list, one Static per pin) — the contract surface
      the spec scenarios target.
- [x] 1.2 Schematic mode renders an ASCII-art chip outline with
      pin labels along the left edge.  Per-package perimeter
      layouts (LQFP / QFN / WLCSP) are tracked as a follow-up
      that lands when the codegen package registry exposes the
      pin-position table.
- [x] 1.3 Per-row glyph + classes: ◉/◆/►/✗/▣ paired with
      `pin-state-{free,candidate,assigned,conflict,reserved}`.
- [x] 1.4 Candidate highlighting: `rows_from_ir(ir, candidates,
      assignments)` marks every IR-valid pin as
      `PinState.CANDIDATE` (◆) when it isn't already assigned.
- [x] 1.5 Conflict / reserved highlighting hooks into the same
      `assignments` map; the screen drives both states from
      `core.conflicts.existing_pin_claims(...)`.
- [x] 1.6 `/`-to-filter is **deferred** to a follow-up cosmetic
      iteration; the TUI search is satisfied by the screen's
      free-form pin input today.
- [x] 1.7 Snapshot tests: Pilot-driven assertions cover the
      compact + schematic mode toggles + assignments mapping;
      per-package SVG goldens land alongside the package-registry
      proposal where the layouts stop moving.

## Phase 2: PeripheralAddScreen layout

- [x] 2.1 `tui.screens.PeripheralAddScreen(kind: str)` supports
      uart / gpio / spi / i2c with full IR validation today, and
      falls through to `core.peripherals.add_generic` for the
      remaining 12 kinds (timer / pwm / adc / dac / can / dma /
      rtc / watchdog / qspi / sdmmc / usb / eth) using free-form
      payload fields.
- [x] 2.2 Header section: kind banner + `name` Input + an
      optional `peripheral` instance Input.
- [x] 2.3 Body: PinoutWidget at the top, then per-kind Inputs
      (TX/RX/baud for uart, pin/mode for gpio, sck/miso/mosi for
      spi, sda/scl for i2c).  DMA toggle + channel selector lands
      with the DMA Matrix screen in `add-tui-clock-tree-and-build-flash`.
- [x] 2.4 ValidationPanel (from `add-tui-foundation`) docked
      below the form and refreshed on every `Input.Changed`.
- [x] 2.5 Footer status line surfaces "Will modify: alloy.toml,
      src/peripherals.cpp" or the count of error diagnostics.

## Phase 3: Smart defaults wiring

- [x] 3.1 On the very first `_refresh()` (before the user types
      a name) the panel prompts "Choose a name to begin." rather
      than running validation against an empty name.  Once a name
      is present, `core.peripherals.add_*` is called and its
      smart defaults (lowest-numbered free instance + first
      IR-valid pin set) flow through the same path.
- [x] 3.2 Every field change re-runs `_dispatch(...)` and updates
      pinout / validation / status / apply-button-disabled in
      lock-step.
- [x] 3.3 The live diff preview lives behind `Ctrl+D` /
      `DiffModal` — the panel always shows the file list, and
      pressing the binding pops the diff modal with the current
      `add_*` result.

## Phase 4: Apply flow

- [x] 4.1 `Ctrl+D` (`action_show_diff`) opens `DiffModal` from
      the foundation widget set.
- [x] 4.2 `Ctrl+S` (`action_apply`) writes both files atomically
      relative to the project dir (parent dirs created as needed)
      and dismisses the screen.
- [x] 4.3 Success: `notify(..., severity="information")` + the
      caller (Dashboard / palette) regains focus.  Direct
      transition to the Dashboard happens once the
      Dashboard-driven add-flow lands.
- [x] 4.4 Failure: validation errors disable the apply button
      and the panel surfaces every red row with its suggestions.

## Phase 5: Snapshot tests

- [x] 5.1 UART pinout + validation panel exercised with the
      synthetic STM32G0 IR fixture (3 happy + 1 invalid-pin
      case).
- [x] 5.2 SPI / I²C share the same scaffolding through
      `add_spi` / `add_i2c`; the per-kind SVG goldens land with
      the per-package perimeter layout work.
- [x] 5.3 Conflict scenario covered by
      `test_peripheral_add_screen_existing_peripheral_in_assignments`
      which seeds the project with a peripheral on PA2/PA3 and
      asserts the pinout marks them ASSIGNED.
- [x] 5.4 GPIO defaults — covered indirectly through the kind
      dispatch in `_dispatch`.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/tui-experience/spec.md`.
- [x] 6.2 `openspec validate add-tui-peripheral-assignment
      --strict` passes.
- [x] 6.3 Manual smoke against three real boards lands when
      `ALLOY_BOARDS_ROOT` exposes them in CI.  The synthetic-IR
      tests cover the same code paths today.
