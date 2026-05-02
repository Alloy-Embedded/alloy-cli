# 02 — UART echo

Reads each byte off USART2 and writes it straight back, while
toggling the LED on every byte so you can confirm activity
without a logic analyser.

## Diff vs `01-blinky`

```diff
+[[peripherals]]
+kind = "uart"
+name = "console"
+peripheral = "USART2"
+tx = "PA2"
+rx = "PA3"
+baud = 115200
```

PA2 / PA3 are the canonical USART2 pins on the Nucleo-G071RB —
they're routed to the ST-Link's virtual COM port, so you only
need a USB cable to see the echo.

## Build + run

```bash
alloy new uart-echo --from-example 02-uart-echo
cd uart-echo
alloy build --profile debug
alloy flash
```

Open the virtual COM port at 115200 8N1 (`screen
/dev/tty.usbmodem* 115200` on macOS, `picocom -b 115200
/dev/ttyACM0` on Linux).  Type into the terminal — every
character comes back.

## Generated code

Look at `.alloy/generated/stm32g071rb/peripherals.cpp` after
`alloy build` runs codegen.  You'll see strongly-typed
`Uart::write()` / `Uart::read()` wrappers around the HAL
register accesses — no register fiddling in your `main.cpp`.

## What's next

[03-spi-flash](../03-spi-flash/) adds an SPI driver against a
synthetic AT25 part — the first multi-peripheral example.
