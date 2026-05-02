# Quickstart — alloy-cli in 5 minutes

This walkthrough takes you from `pip install` to a flashed
Nucleo-G071RB blinking its on-board LED.  Time to first ELF on
a fresh machine: ~5 minutes.

## Prerequisites

- Python 3.11+ (3.13 recommended)
- `arm-none-eabi-gcc` 14+ on `$PATH`
- `cmake` 3.27+, `ninja` 1.11+
- `probe-rs` 0.24+ (for flashing) and an ST-Link probe
- A Nucleo-G071RB (any STM32G0 board with the `nucleo_g071rb`
  ID works)

If anything's missing, run `alloy doctor --fix` after
installing — it auto-installs the optional `mcp` Python
extra and initialises the data submodule.

## 1. Install

```bash
pip install alloy-cli
alloy --version          # confirms the install
```

## 2. Scaffold

```bash
alloy new blinky --board nucleo_g071rb
cd blinky
```

You'll get an `alloy.toml`, a thin `CMakeLists.txt`, and a
`src/main.cpp` skeleton wired to the board's LED.

## 3. Add an LED + UART

```bash
alloy add gpio  --name led       --pin PA5  --mode output --apply
alloy add uart  --name console   --peripheral USART2 --tx PA2 --rx PA3 --apply
```

The CLI validates every pin against the device IR — invalid
combos raise structured diagnostics with suggestions.  See
[ERROR_COOKBOOK.md](ERROR_COOKBOOK.md) when something
explodes.

## 4. Build

```bash
alloy build --profile debug
```

Expected output (truncated):

```
[codegen] regenerating stm32g071rb via alloy-codegen 0.4.x
[cmake] -- The C compiler identification is GNU
[ninja] [12/12] Linking CXX executable blinky.elf
```

The ELF lands at `.alloy/build/blinky.elf`.

## 5. Flash

Plug your Nucleo in, then:

```bash
alloy flash
```

probe-rs auto-discovers the ST-Link, programs the firmware,
and resets the chip.  The on-board LED should now blink at
~1 Hz.

## What just happened

- `alloy new --board nucleo_g071rb` resolved the board to the
  STM32G071RB chip via `alloy-devices-yml`.
- `alloy add gpio / uart` validated the pin choices against
  the IR's connection candidates (PA5 is an output pin, PA2 /
  PA3 are USART2's TX / RX).
- `alloy build` ran alloy-codegen → cmake → ninja.  Every
  step is cached on a stamp keyed by the IR SHA + alloy-cli
  version, so a no-op rebuild lands in a few hundred ms.
- `alloy flash` invoked `probe-rs run` against the ELF.

## Next steps

- Open the TUI: `alloy ui`.  Press `Ctrl+P` for the command
  palette; `d` opens Doctor; `c` opens the Clock Tree.
- Browse the [progressive examples](EXAMPLES/) — UART echo,
  SPI flash, DMA double-buffer.
- Hook up your AI agent: `alloy chat` (see
  [AI_INTEGRATION.md](AI_INTEGRATION.md)).
- When something breaks, run `alloy doctor` — every error
  type is documented in [ERROR_COOKBOOK.md](ERROR_COOKBOOK.md).
