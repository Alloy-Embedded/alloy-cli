# Quickstart — alloy-cli in 5 minutes

This walkthrough takes you from `pip install` to a flashed
Nucleo-G071RB blinking its on-board LED.  Time to first ELF on a
fresh machine: about 5 minutes — the bulk of which is downloading
the family's toolchain (~290 MB across 5–6 binaries).

## Prerequisites

Just the basics — alloy-cli installs the rest:

- Python 3.11+ (3.13 recommended)
- A Nucleo-G071RB (or any STM32G0 board with the `nucleo_g071rb`
  ID — run `alloy boards` to see the catalogue)
- An ST-Link probe (the on-board ST-Link on the Nucleo works)

You do **not** need to pre-install `arm-none-eabi-gcc`, `cmake`,
`ninja`, or `probe-rs`.  The post-scaffold prompt below downloads
them into a per-user content-addressed store and pins the SHAs in
`.alloy/toolchain.lock`.

> If you already manage your toolchain externally (system
> arm-gcc, conda env, Docker container), pass
> `--no-install-toolchain` on the `alloy new` line below — your
> existing PATH is honoured untouched.

## 1. Install alloy-cli

```bash
pip install alloy-cli
alloy --version          # confirms the install
```

## 2. Scaffold + install the toolchain

```bash
alloy new firmware --board nucleo_g071rb     # answer Y when prompted
cd firmware
```

After scaffolding finishes, alloy prints the install plan (every
tool it would download, with sizes and SHAs) and asks
`Install toolchain now? [Y/n]`.  Answer `Y` (the default) and the
4 required tools install into the per-user store; STM32CubeProgrammer
(vendor, EULA-gated) is **never** auto-fetched — alloy prints its
install_doc URL instead.

The whole thing takes about 90 seconds on a 100 Mbit/s connection.

> **CI users:** `alloy new --board nucleo_g071rb` in a non-TTY
> context (closed STDIN) skips the install by default — pass
> `--install-toolchain --auto` to opt in non-interactively, or
> `--no-install-toolchain` to skip explicitly.

## 3. Build

```bash
alloy build
```

Expected output (truncated):

```
[codegen] regenerating stm32g071rb via alloy-codegen 0.4.x
[cmake] -- The C compiler identification is GNU
[ninja] [12/12] Linking CXX executable firmware.elf
```

The ELF lands at `.alloy/build/firmware.elf`.  The compiler picked
up automatically from `.alloy/toolchain.lock` — no PATH wrangling.

## 4. Flash

Plug your Nucleo in, then:

```bash
alloy flash
```

probe-rs auto-discovers the ST-Link, programs the firmware, and
resets the chip.  The on-board LED should now blink at ~1 Hz.

## 6. Reset + monitor (optional)

Once the firmware is on the chip, the recovery primitives let you
poke at it without leaving alloy-cli:

```bash
alloy reset                                  # CPU reset
alloy monitor --port /dev/cu.usbmodem1234    # press Ctrl+] to disconnect
```

`alloy reset` is non-destructive — the firmware on the chip stays
put.  `alloy monitor` opens the explicit serial port at 115200
baud (or whatever your project's `[uart].debug` declares).
`alloy erase` exists for recovering from a brick but is gated
behind a TTY confirmation prompt by default; pass `--auto` /
`--yes` to bypass in CI.  See
[RECOVERY.md](RECOVERY.md) for the full reference.

## I cloned an existing project — what now?

```bash
git clone <repo>
cd <repo>
alloy doctor --fix
```

`alloy doctor --fix` walks the family declared in `alloy.toml`,
notices which tools are missing from the local store, and installs
each through the same shared orchestrator the post-scaffold prompt
uses.  Vendor tools surface as info rows with their install_doc URL
— never auto-fetched.

## What just happened

- `alloy new --board nucleo_g071rb` resolved the board to the
  STM32G071RB chip via `alloy-devices-yml`, then dispatched the
  post-scaffold install through
  `toolchain_orchestrator.install_family` — the same code path
  `alloy doctor --fix`, `alloy setup`, the TUI Onboarding screen,
  and the MCP `toolchain_apply_install_plan` tool all use.
- `alloy build` ran alloy-codegen → cmake → ninja, picking up the
  pinned compiler from `.alloy/toolchain.lock`.  Every step is
  cached on a stamp keyed by the IR SHA + alloy-cli version.
- `alloy flash` invoked `probe-rs run` against the ELF — using the
  pinned `probe-rs` binary, not whatever happens to be on PATH.

## Next steps

- Read [TOOLCHAIN_ONBOARDING.md](TOOLCHAIN_ONBOARDING.md) for the
  full reference: the four entry points, the shared orchestrator
  API, the two-phase MCP pattern, and the cancellation contract.
- Open the TUI: `alloy ui`.  Press `Ctrl+P` for the command
  palette; `d` opens Doctor; `c` opens the Clock Tree.
- Browse the [progressive examples](EXAMPLES/) — UART echo,
  SPI flash, DMA double-buffer.
- Hook up your AI agent: `alloy chat` (see
  [AI_INTEGRATION.md](AI_INTEGRATION.md)).
- When something breaks, run `alloy doctor` — every error type is
  documented in [ERROR_COOKBOOK.md](ERROR_COOKBOOK.md).
