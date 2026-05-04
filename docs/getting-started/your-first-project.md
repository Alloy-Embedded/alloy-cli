# Your first project

The [Quickstart](../QUICKSTART.md) gets you to a flashed Nucleo
in five minutes.  This page goes deeper: it shows what's
actually happening at each step, walks through adding a UART +
GPIO with the IR-validated pin picker, and explains the
toolchain lockfile.

## What you'll build

A minimal STM32G071RB project that:

- Blinks the on-board LED (LD4 on PA5).
- Echoes characters typed on the debug UART (USART2 on PA2 / PA3).

Plus the alloy-cli concepts you'll touch:

- The post-scaffold install prompt + `.alloy/toolchain.lock`.
- IR validation when adding a peripheral.
- The two-phase preview-then-apply pattern.
- `alloy build` reading the lockfile to resolve `arm-none-eabi-gcc`.

## Step 1 — scaffold

```bash
alloy new firmware --board nucleo_g071rb
```

You'll see a Rich panel listing every tool the family will
install (xpack arm-gcc 14.x, cmake 3.31, ninja 1.12, probe-rs
0.27, plus STM32CubeProgrammer rendered as `vendor — install
manually`).  The total is **~290 MB** for the stm32g0 family on
a 100 Mbit/s connection that's about 90 seconds.

Answer **Y**.  Watch the live progress for each tool:

```text
  → arm-none-eabi-gcc@14.2.1-1.1 (xpack, 198 MiB)
    downloaded 198 MiB
  ✓ arm-none-eabi-gcc@14.2.1-1.1 installed
  → cmake@3.31.2 (xpack, 42 MiB)
  …
```

When it finishes:

```bash
cd firmware
ls -la .alloy/
# .alloy/toolchain.lock     ← the SHA-pinned manifest
```

The lockfile has one entry per tool that landed in the
content-addressed store.  See
[Lockfile-aware execution](../concepts/lockfile-aware-execution.md)
for what reads it.

## Step 2 — see what scaffolding gave you

```bash
ls -la
# alloy.toml          ← project manifest
# CMakeLists.txt      ← thin (~30 lines); reads the lockfile
# src/main.cpp        ← skeleton with the LED blink
# README.md           ← project-specific notes
# .gitignore          ← .alloy/build/ + .alloy/cache/ ignored
# LICENSE             ← MIT by default; use --license to override
```

Open `alloy.toml`:

```toml
schema_version = "1.1.0"

[project]
name = "firmware"

[board]
id = "nucleo_g071rb"

[clocks]
profile = "default_pll_64mhz"

[[peripherals]]
kind = "gpio"
name = "led"
pin = "PA5"
mode = "output"

[[peripherals]]
kind = "uart"
name = "console"
peripheral = "USART2"
tx = "PA2"
rx = "PA3"
baud = 115200
```

The `[board]` table tells alloy-cli "look up the
`nucleo_g071rb` manifest for chip / family / clock / pin
defaults."  The `[[peripherals]]` entries are the project-level
wiring.

## Step 3 — add a second peripheral

Let's add a second GPIO bound to the user button (B1 on PC13):

```bash
alloy add gpio --name button --pin PC13 --mode input --pull up
```

The output shows the IR validation in action:

```text
[preview]
  + [[peripherals]]
  +   kind = "gpio"
  +   name = "button"
  +   pin = "PC13"
  +   mode = "input"
  +   pull = "up"

  IR validation: PC13 is on PORTC; available as digital input;
                 internal pull-up supported.
                 No conflict with existing peripherals.

apply this diff? [y/N]:
```

Answer **y**.  alloy.toml updates atomically.  If you'd typed a
pin that doesn't exist, you'd see:

```text
PinInvalidError: PZ99 is not a pin on stm32g071rb.
  candidates: PA0, PA1, PA2, PA3, …  (87 total)
  → see docs/ERROR_COOKBOOK.md#PinInvalidError
```

The error_type is stable; LLM agents on the MCP transport branch
on it and call `suggest_pins` to recover.

## Step 4 — build

```bash
alloy build
```

Three things happen:

1. **Codegen**: `alloy-codegen` reads `alloy.toml`, consults the
   IR, regenerates `.alloy/cache/peripherals.cpp` (and any
   board-specific bits).  Cached on the IR SHA + alloy-cli
   version — no-op rebuilds land in milliseconds.
2. **CMake configure**: cmake reads `.alloy/toolchain.lock` to
   resolve `arm-none-eabi-gcc` to its absolute path in the
   content-addressed store.  No PATH munging.
3. **Ninja build**: links the ELF.

Output:

```text
[codegen] regenerating stm32g071rb via alloy-codegen 0.4.x
[cmake] -- The C compiler identification is GNU 14.2.0
[cmake] Build files written to: .alloy/build
[ninja] [12/12] Linking CXX executable firmware.elf
```

## Step 5 — flash

Plug the Nucleo in.  Then:

```bash
alloy flash
```

`probe-rs` (resolved from the lockfile) auto-discovers the
ST-Link, programs the ELF, resets the chip.  The on-board LED
blinks at ~1 Hz.

## Step 6 — monitor

```bash
alloy monitor --port /dev/cu.usbmodem1234
```

Type a few characters; they echo back.  Press **Ctrl+]** to
disconnect.  The summary prints byte count + duration + last
line.

## What you didn't have to do

- Install arm-gcc / cmake / ninja / probe-rs manually.
- Edit `CMakeLists.txt` for the chip, the linker script, the
  startup code, the assembly flags, the optimisation level — all
  of that is generated from `alloy.toml`.
- Pick GPIO ports + clock dividers from a 1,500-page reference
  manual.  The IR did it.

## Where to go next

- **[Toolchain onboarding](../TOOLCHAIN_ONBOARDING.md)** — every
  entry point that installs a per-family toolchain (you used
  `alloy new --install-toolchain`; there are four others).
- **[AI integration](../AI_INTEGRATION.md)** — wire your project
  into Claude / opencode / Cursor via MCP.
- **[Recovery](../RECOVERY.md)** — `alloy reset` / `alloy erase`
  for when the chip is misbehaving.
- **[Examples](../EXAMPLES/01-blinky/README.md)** — four
  progressive examples (blinky, UART echo, SPI flash, DMA
  double-buffer).
