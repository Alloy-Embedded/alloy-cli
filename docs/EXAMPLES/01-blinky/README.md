# 01 — Blinky

The minimum viable firmware: toggle the board's on-board LED.

## What's in `alloy.toml`

- `[board] id = "nucleo_g071rb"` resolves to the STM32G071RB
  chip + the LD4 user LED on PA5.
- One `[[peripherals]]` entry — `kind = "gpio"` driving PA5
  as a digital output with `initial = 0` so the firmware
  starts with the LED off.

## Build it

```bash
alloy new blinky --from-example 01-blinky
cd blinky
alloy build --profile debug
alloy flash
```

The on-board LED should now toggle in your firmware's main
loop (left as the developer-friendly first edit in
`src/main.cpp`).

## What's next

[02-uart-echo](../02-uart-echo/) adds a typed UART so you can
print `printf` traces over the ST-Link's virtual COM port.
