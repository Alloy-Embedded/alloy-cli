# Tasks — add-cli-add-peripheral

## Phase 1: Core operations (per kind)

- [ ] 1.1 `core.peripherals.add_gpio(config, args) -> AddResult`
- [ ] 1.2 `core.peripherals.add_uart(config, args) -> AddResult`
- [ ] 1.3 `core.peripherals.add_spi(config, args)`
- [ ] 1.4 `core.peripherals.add_i2c(config, args)`
- [ ] 1.5 `core.peripherals.add_timer(config, args)`
- [ ] 1.6 `core.peripherals.add_pwm(config, args)`
- [ ] 1.7 `core.peripherals.add_adc(config, args)`
- [ ] 1.8 `core.peripherals.add_dac(config, args)`
- [ ] 1.9 `core.peripherals.add_can(config, args)`
- [ ] 1.10 `core.peripherals.add_dma_channel(config, args)` (raw,
       for advanced users)
- [ ] 1.11 `core.peripherals.add_rtc(config, args)`
- [ ] 1.12 `core.peripherals.add_watchdog(config, args)`
- [ ] 1.13 `core.peripherals.add_qspi(config, args)`
- [ ] 1.14 `core.peripherals.add_sdmmc(config, args)`
- [ ] 1.15 `core.peripherals.add_usb(config, args)`
- [ ] 1.16 `core.peripherals.add_eth(config, args)`

Every operation returns `AddResult { diff: UnifiedDiff,
diagnostics: tuple[Diagnostic] }`.  No I/O.

## Phase 2: Validators

- [ ] 2.1 `core.pins.validate_assignment(device, pin, signal) ->
      Diagnostic | None` using `connection_candidates`.
- [ ] 2.2 `core.dma.validate_channel(device, peripheral, direction,
      channel) -> Diagnostic | None` using `dma_routes`.
- [ ] 2.3 `core.clocks.validate_baud(device, peripheral_clock_hz,
      baud) -> Diagnostic | None` using `uart_max_baud_hz` etc.
- [ ] 2.4 `core.conflicts.detect(config, proposed) ->
      tuple[Conflict, ...]` — checks pin / DMA / interrupt
      overlaps with existing peripherals.

## Phase 3: Smart defaults

- [ ] 3.1 `core.suggestions.suggest_peripheral(device, kind,
      existing) -> str` — pick lowest free instance.
- [ ] 3.2 `core.suggestions.suggest_pins(device, peripheral, kind)
      -> tuple[PinSuggestion, ...]` — pick first non-conflicting
      candidate set.
- [ ] 3.3 `core.suggestions.suggest_dma(device, peripheral,
      direction, existing) -> DmaChannelId | None` — lowest free
      channel.

## Phase 4: CLI command

- [ ] 4.1 `cli.add` Click command group with one subcommand per
      kind.
- [ ] 4.2 `--apply` vs `--diff-only` toggle (default behaviour:
      diff-only).
- [ ] 4.3 Pretty diff via `rich.console`.
- [ ] 4.4 Diagnostics rendered in colour with severity icons.

## Phase 5: Source emit

- [ ] 5.1 `core.emit.peripherals_cpp(config) -> str` — generates
      the contents of `src/peripherals.cpp` from the full
      `[[peripherals]]` list.  Idempotent: re-running produces
      identical bytes.
- [ ] 5.2 `core.emit.split_emit_targets(config) -> dict[Path,
      str]` — currently `{Path("alloy.toml"), Path("src/peripherals.cpp")}`
      but extensible.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in
      `specs/peripheral-operations/spec.md` and
      `specs/cli-surface/spec.md`.
- [ ] 6.2 `openspec validate add-cli-add-peripheral --strict`
      passes.
- [ ] 6.3 Smoke: 8 admitted boards × 4 representative peripherals
      = 32 add-and-build smoke tests.
