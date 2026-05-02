# Enrich Peripheral Kinds: Timer / PWM / ADC / DAC / CAN / USB / Eth

## Why

Schema v1.0.0 only validates `uart / gpio / spi / i2c` deeply.  The
remaining 12 kinds (timer, pwm, adc, dac, can, dma, rtc, watchdog,
qspi, sdmmc, usb, eth) round-trip through `core.peripherals.add_generic`
with **zero validation**.  A user can write a `[[peripherals]]`
block with `kind="timer"` and any payload — we'll happily emit it.

That breaks the headline contract: *"every choice is validated against
a typed device IR at config time."*

This proposal closes the gap for the seven highest-impact kinds
(timer, pwm, adc, dac, can, usb, eth) and tightens the auto-DMA
suggestion logic so `--dma` actually picks a channel.

## What Changes

### Schema bump → `1.1.0`

- `schema/alloy_toml_v1_1.json` — adds per-kind `if/then` blocks
  for `timer`, `pwm`, `adc`, `dac`, `can`, `usb`, `eth`.  The old
  schema ID is bumped from `1.0.0` to `1.1.0` (additive — old
  files validate against the new schema).
- `core.project._check_schema_version` accepts both `1.0.x` and
  `1.1.x`.
- `core.project.PROJECT_SCHEMA_VERSION` constant updated; existing
  scaffolds bump on next write.

### Typed `add_<kind>` operations

For each newly-typed kind, a typed function in
`core.peripherals`:

```
add_timer(config, ir, args)  # period_ns / divider / mode
add_pwm(config, ir, args)    # pin + duty_cycle + frequency_hz
add_adc(config, ir, args)    # channel(s) + sample_time + resolution
add_dac(config, ir, args)    # channel + output_buffer
add_can(config, ir, args)    # tx/rx pins + bitrate + sample_point
add_usb(config, ir, args)    # device|host|otg + vbus_sense
add_eth(config, ir, args)    # mii|rmii + phy_address + pin set
```

Each validates against the IR's peripheral list, applies the smart
defaults already used by uart/gpio/spi/i2c, and produces the same
`AddResult` shape.

### Auto-DMA wiring

- `add_uart`, `add_spi`, `add_i2c` are extended: when the user
  passes `--dma` *without* `--tx-dma` / `--rx-dma`,
  `core.suggestions.suggest_dma` is called per direction and the
  picked channels flow into the payload.
- `core.suggestions.suggest_dma_pair(ir, peripheral)` returns a
  `DmaPair { tx, rx }` so peripherals that need both directions
  get a consistent allocation.

### CLI subcommands

- `alloy add timer / pwm / adc / dac / can / usb / eth` — Click
  subcommands mirroring the existing `uart / gpio / spi / i2c`
  surface.
- `alloy add --kind <name>` becomes the discoverable shortcut for
  scripted users.

### MCP coverage

- New tools: `alloy.add_timer / pwm / adc / dac / can / usb / eth`
  delegating to the typed operations.

## Impact

After this proposal, **every peripheral kind a user can pin in
their alloy.toml is type-checked at config time**.  The
hallucination-defence story extends from 4 kinds to 11.

The auto-DMA fix removes a "you said `--dma` but I didn't pick a
channel" trap door that today silently corrupts deterministic
emission (the diff says `dma=true` but the .cpp file doesn't
generate the DMA setup).

## What this DOES NOT do

- Does not extend to `dma / rtc / watchdog / qspi / sdmmc` — they
  stay generic for now (their schemas need more thought; rtc/
  watchdog have OS-level interactions).
- Does not change the CLI flag spelling for the existing four
  kinds; the new flags are additive.
- Does not introduce a peripheral-removal command (`alloy remove
  <name>` is still future work).
- Does not bump beyond major 1; `_check_schema_version` keeps the
  major-only guard.
