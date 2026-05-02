# Add `alloy add` Peripheral Wiring

## Why

This is the **first feature where alloy-cli pulls ahead of the
incumbents**.  CubeMX has the GUI version; PlatformIO has nothing
in the same league; Modm needs Python config files.

`alloy add <kind>` adds a peripheral to the project — fully
validated against the canonical IR — without ever opening a TUI.
The TUI in Phase 3 is a façade over this command's core
operations.

## What Changes

### Command surface

```
alloy add uart   --name N --peripheral USART1 --tx PIN --rx PIN
                 [--baud N] [--data-bits 7|8|9] [--stop 1|0.5|1.5|2]
                 [--parity none|even|odd] [--dma]
                 [--tx-dma DMA1_CH1] [--rx-dma DMA1_CH2]
                 [--apply | --diff-only]

alloy add gpio   --name N --pin PIN --mode input|output|od
                 [--pull none|up|down] [--speed low|medium|high]
                 [--label LABEL] [--initial 0|1]

alloy add spi    --name N --peripheral SPI1 --sck PIN --miso PIN
                 --mosi PIN [--cs PIN | --cs-software]
                 [--mode 0..3] [--bit-order msb|lsb]
                 [--frame 8|16] [--prescaler N] [--dma]

alloy add i2c    --name N --peripheral I2C1 --sda PIN --scl PIN
                 [--speed standard|fast|fast-plus]
                 [--addressing 7|10] [--dma]

# Plus: timer, pwm, adc, dac, can, dma (raw), rtc, watchdog,
# qspi, sdmmc, usb, eth — same pattern.
```

### Behaviour

- Reads `alloy.toml`; loads device IR via `core.ir.load_device`.
- For each pin / DMA / clock decision, queries the IR for valid
  options and validates the user's choices.
- If `--peripheral` is omitted, picks the lowest-numbered free
  instance.
- If `--tx` / `--rx` (etc.) are omitted, picks the first
  candidate pair from `connection_candidates[(pin, signal)]`
  that doesn't conflict with existing assignments.
- If `--dma` is set without explicit channel, picks the
  lowest-numbered free channel from `dma_routes[peripheral][TX]`.
- Validates: pin is in connection_candidates, DMA channel is in
  dma_routes, baud rate fits, no conflict with existing
  peripherals.
- On success: produces a unified diff for `alloy.toml` (always)
  and any `src/peripherals.cpp` insertion.
- `--apply` writes the diff atomically.  `--diff-only` (default
  when no `--apply` given) prints the diff and exits 0.

### Core operations

`core.peripherals.add_uart(...)`, `add_gpio(...)`, …  Each
returns a `UnifiedDiff` and a list of `Diagnostic`s.  No
filesystem mutation in `core/`; the CLI applies.

This is the contract Phase 3 (TUI) and Phase 4 (MCP) wrap.

## Impact

The killer-app feature, in CLI form, with no TUI dependency.  Even
without the TUI, this is already ahead of PlatformIO + Modm.

## What this DOES NOT do

- No interactive picker — that's the TUI in
  `add-tui-peripheral-assignment`.
- No removal — `alloy remove <peripheral>` is a follow-up (post-MVP).
- No conflict-resolution wizard — when a user requests a conflicting
  pin, the command exits with a clear error and a list of free
  candidates; we don't prompt mid-CLI.
- No multi-peripheral atomic add (`alloy add uart && alloy add gpio
  ...` is two commands).
