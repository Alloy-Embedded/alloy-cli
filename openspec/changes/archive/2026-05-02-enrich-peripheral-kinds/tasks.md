# Tasks — enrich-peripheral-kinds

## Phase 1: Schema bump

- [x] 1.1 `schema/alloy_toml_v1_1.json` — additive update with
      `if/then` blocks for timer / pwm / adc / dac / can / usb /
      eth.  ADC channels modelled as an array of objects with
      `channel` + `pin`.
- [x] 1.2 `core.project._check_schema_version` accepts every
      `1.x.x`; the validator pulls v1.1 first and falls back to
      v1.0 on older installs.
- [x] 1.3 `core.project.SCHEMA_VERSION` bumped to `"1.1.0"`;
      `core.scaffold` writes the new version on fresh projects
      automatically.
- [x] 1.4 Migration: existing `1.0.0` files keep validating
      (the new `if/then` blocks only fire when their `kind`
      matches; an existing `kind="uart"` block is unchanged).

## Phase 2: Typed add operations

- [x] 2.1 `core.peripherals.add_timer` — peripheral picker +
      mandatory `period_ns` + optional divider/mode/interrupt.
- [x] 2.2 `core.peripherals.add_pwm` — channel-aware pin
      validation against `connection_candidates(peripheral,
      signal=f"CH{channel}")`.
- [x] 2.3 `core.peripherals.add_adc` — multi-channel payload;
      each entry validated as `(channel, pin)` against the
      ADC's `IN<n>` candidates.
- [x] 2.4 `core.peripherals.add_dac` — pin validated against
      `OUT<channel>` candidates.
- [x] 2.5 `core.peripherals.add_can` — TX/RX pin set + bitrate
      / sample_point / fd extras.
- [x] 2.6 `core.peripherals.add_usb` — enum validation on
      `mode in {device, host, otg}`.
- [x] 2.7 `core.peripherals.add_eth` — accepts MII / RMII +
      phy_address + per-pin overrides.

## Phase 3: Auto-DMA

- [x] 3.1 `core.suggestions.suggest_dma_pair(ir, peripheral,
      existing) -> DmaPair { tx, rx }` honouring existing
      claims; picks TX first then RX from the remaining routes.
- [x] 3.2 `add_uart` / `add_spi` / `add_i2c` call
      `suggest_dma_pair` whenever `--dma` is set without
      explicit `--tx-dma` / `--rx-dma` overrides.
- [x] 3.3 The chosen channels flow through
      `core.project._toml_value` (which now supports inline
      tables) so the diff payload is byte-stable on round-trip.

## Phase 4: CLI + MCP

- [x] 4.1 Click subcommands `alloy add timer / pwm / adc / dac
      / can / usb / eth` mirror the existing surface.  ADC
      uses repeatable `--channel N:PIN` syntax.
- [x] 4.2 MCP tools wrapping each new operation; descriptors
      surface preconditions + side effects, schemas pinned in
      `_PARAM_SCHEMA`.
- [x] 4.3 `_KIND_DISPATCH` extended so `preview_diff(kind=...)`
      reaches the typed paths automatically.

## Phase 5: Tests

- [x] 5.1 `tests/test_peripheral_kinds_v1_1.py` (21 cases)
      covers each kind: missing required field → diagnostic,
      pin validation, default instance pick, enum rejection,
      and happy paths.
- [x] 5.2 Auto-DMA: pair picks TX/RX automatically, explicit
      overrides win, no-routes raises `no-dma-channels`,
      `suggest_dma_pair` skips claimed channels.
- [x] 5.3 Schema regression: 1.0.0 files still parse, 1.1.0
      timer without `period_ns` fails with
      `peripherals/0/period_ns`, USB invalid `mode` raises
      `schema validation`.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/peripheral-operations/spec.md`
      and `specs/project-format/spec.md`.
- [x] 6.2 `openspec validate enrich-peripheral-kinds --strict`
      passes.
- [x] 6.3 `docs/PROJECT_FORMAT.md` peripheral-kind matrix lands
      in a follow-up doc-only PR — the spec already pins the
      contract.
