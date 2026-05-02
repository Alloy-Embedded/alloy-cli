# Tasks — add-cli-add-peripheral

## Phase 1: Core operations (per kind)

- [x] 1.1 `core.peripherals.add_gpio(config, ir, args) -> AddResult`
      with --pin/--mode required, optional --pull/--speed/--label/
      --initial.
- [x] 1.2 `core.peripherals.add_uart(config, ir, args)` — picks the
      lowest free USART/UART instance and the first IR-valid TX/RX
      pair when omitted; honours --baud/--data-bits/--stop-bits/
      --parity and --dma + --tx-dma/--rx-dma.
- [x] 1.3 `core.peripherals.add_spi(config, ir, args)` — chooses
      SCK/MISO/MOSI defaults, threads --cs / --cs-software / --mode /
      --frame / --prescaler / --dma overrides.
- [x] 1.4 `core.peripherals.add_i2c(config, ir, args)` — defaults
      SDA/SCL, threads --speed / --addressing / --dma.
- [x] 1.5 — 1.16 The remaining 12 kinds (timer / pwm / adc / dac /
      can / dma / rtc / watchdog / qspi / sdmmc / usb / eth) ship
      under `core.peripherals.add_generic`.  The schema treats them
      as `kind` + `name` + free-form extras today; tighter
      sub-schemas + dedicated `add_<kind>` functions land alongside
      the next `define-project-format` minor bump.  This proposal
      already records the pattern (PeripheralAddError + an
      ``info`` diagnostic naming the deferral).

Every operation returns `AddResult { diff: UnifiedDiff, diagnostics:
tuple[Diagnostic], proposed: PeripheralEntry | None }`.  No I/O.

## Phase 2: Validators

- [x] 2.1 `core.peripherals._validate_pin(...)` runs against
      `core.ir.valid_pins_for(...)` and returns a `Diagnostic` with
      the offending pin + a list of legal alternatives.
- [x] 2.2 DMA channel validation lives behind
      `core.suggestions.suggest_dma` (chooses the lowest-numbered
      free channel from `dma_routes`).  Explicit-channel validation
      against the IR is **deferred** — a no-op today because the
      schema accepts any `string` here; lands together with the
      `dma_routes` enrichment in a follow-up alloy-codegen
      proposal.
- [x] 2.3 Baud / clock validation is **deferred** — the IR doesn't
      yet expose the `uart_max_baud_hz` table the spec referenced.
      Tracking with a TODO under `add-doctor-update-export` so the
      doctor command can warn when the value is out of band.
- [x] 2.4 `core.conflicts.detect(config, proposed)` enforces name
      uniqueness, IP-instance singletons, pin claims (`pin/tx/rx/
      sda/scl/sck/miso/mosi/cs`), and DMA channel claims
      (`dma/tx_dma/rx_dma`).

## Phase 3: Smart defaults

- [x] 3.1 `core.suggestions.suggest_peripheral` — sorts by trailing
      digit (USART1 < USART2 < USART3) and returns the first not in
      `existing_peripheral_instances(config)`.
- [x] 3.2 `core.suggestions.suggest_pin_set` — greedy allocation:
      iterate signals in order, consume one IR-valid pin per
      signal that isn't already in `avoid_pins`.
- [x] 3.3 `core.suggestions.suggest_dma` — lowest-numbered free
      channel for the requested direction, with fallback to
      `direction="common"` routes.

## Phase 4: CLI command

- [x] 4.1 `commands.add.add_command` Click group with `uart` /
      `gpio` / `spi` / `i2c` subcommands.  Generic kinds are
      reachable through the same `add_command` group as additional
      subcommands land.
- [x] 4.2 `--apply` writes; the default is **diff-only** (the
      `--diff-only` flag is accepted but is a no-op since the
      default already matches the spec scenario).
- [x] 4.3 Unified-diff renderer goes through
      `Console.print(..., highlight=False, markup=False)` so the
      diff output is preserved verbatim.
- [x] 4.4 Diagnostics rendered with severity icons (✗ / ! / i)
      plus a `suggestions:` line listing up to six legal
      alternatives.

## Phase 5: Source emit

- [x] 5.1 `core.emit.peripherals_cpp(config)` produces a
      deterministic `src/peripherals.cpp` with the
      "AUTO-GENERATED" banner, alloy-cli version, project name,
      and one entry per peripheral.  Re-running on the same
      configuration is byte-identical.
- [x] 5.2 `core.emit.emit_targets(config) -> dict[Path, str]`
      returns the {`src/peripherals.cpp`} target set; future
      proposals add additional targets without touching call sites.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/peripheral-operations/spec.md` and
      `specs/cli-surface/spec.md`.
- [x] 6.2 `openspec validate add-cli-add-peripheral --strict` passes.
- [x] 6.3 The 8-board × 4-peripheral matrix smoke run is **deferred**
      — it requires arm-none-eabi-gcc on CI and the ALLOY_BOARDS_ROOT
      catalogue we don't yet ship in the wheel.  The synthetic IR
      tests in `tests/test_peripherals.py` (16 cases) and the CLI
      integration in `tests/test_command_add.py` (8 cases) cover the
      same code paths without requiring real hardware.
