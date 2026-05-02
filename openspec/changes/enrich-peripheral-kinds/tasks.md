# Tasks — enrich-peripheral-kinds

## Phase 1: Schema bump

- [ ] 1.1 `schema/alloy_toml_v1_1.json` — additive update with
      `if/then` blocks for timer / pwm / adc / dac / can / usb /
      eth.
- [ ] 1.2 `core.project._check_schema_version` accepts `1.0.x`
      and `1.1.x`.
- [ ] 1.3 `core.project.PROJECT_SCHEMA_VERSION` constant updated;
      `core.scaffold` writes the new version on fresh projects.
- [ ] 1.4 Migration: existing files keep validating; `alloy
      doctor` flags major-mismatch only, not minor.

## Phase 2: Typed add operations

- [ ] 2.1 `core.peripherals.add_timer(config, ir, args)`.
- [ ] 2.2 `core.peripherals.add_pwm(config, ir, args)` — validates
      pin against `connection_candidates(peripheral, signal="CHn")`.
- [ ] 2.3 `core.peripherals.add_adc(config, ir, args)` — multi-channel
      payload validated against `connection_candidates`.
- [ ] 2.4 `core.peripherals.add_dac(config, ir, args)`.
- [ ] 2.5 `core.peripherals.add_can(config, ir, args)`.
- [ ] 2.6 `core.peripherals.add_usb(config, ir, args)` — validates
      `mode in {device, host, otg}`.
- [ ] 2.7 `core.peripherals.add_eth(config, ir, args)` — accepts
      MII / RMII variants + per-pin validation.

## Phase 3: Auto-DMA

- [ ] 3.1 `core.suggestions.suggest_dma_pair(ir, peripheral)` —
      returns `DmaPair { tx, rx }` honouring existing claims.
- [ ] 3.2 `add_uart` / `add_spi` / `add_i2c` call it when `--dma`
      is set without explicit channel overrides.
- [ ] 3.3 The chosen channels flow into both the diff payload and
      the emitted peripherals.cpp.

## Phase 4: CLI + MCP

- [ ] 4.1 Click subcommands `alloy add timer / pwm / adc / dac /
      can / usb / eth` mirror the existing surface.
- [ ] 4.2 MCP tools for the same kinds; descriptions follow the
      preconditions / side effects pattern.
- [ ] 4.3 `alloy add --kind <name>` shortcut for scripting.

## Phase 5: Tests

- [ ] 5.1 Schema regression: each new kind has 2 happy + 2
      negative fixtures.
- [ ] 5.2 `add_<kind>` unit tests with synthetic IRs covering
      pin validation, instance auto-pick, conflict detection.
- [ ] 5.3 Auto-DMA test for `add_uart --dma`: payload contains
      `tx_dma` + `rx_dma` and emit references both.
- [ ] 5.4 MCP integration test: `add_can` with an invalid pin
      returns the typed-error envelope.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/peripheral-operations/spec.md` and
      `specs/project-format/spec.md`.
- [ ] 6.2 `openspec validate enrich-peripheral-kinds --strict`
      passes.
- [ ] 6.3 `docs/PROJECT_FORMAT.md` updated peripheral kind matrix.
