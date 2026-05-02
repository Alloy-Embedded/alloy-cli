# 04 — DMA double-buffered UART

The same UART echo as `02-uart-echo`, but with DMA on both
TX and RX so the CPU stays free while characters move
through the bus.  This is the recommended pattern for any
production-grade UART workload.

## Diff vs `02-uart-echo`

```diff
 [[peripherals]]
 kind = "uart"
 name = "console"
 peripheral = "USART2"
 tx = "PA2"
 rx = "PA3"
 baud = 115200
+dma = true
+tx_dma = "DMA1#1"
+rx_dma = "DMA1#2"
```

`dma = true` would auto-allocate via
`core.suggestions.suggest_dma_pair` if you didn't pin the
channels.  Pinning them keeps the example reproducible across
machines that may have other peripherals competing for the
DMA controller.

## Build + run

```bash
alloy new dma-double-buffer --from-example 04-dma-double-buffer
cd dma-double-buffer
alloy build --profile debug
alloy flash
```

After the next `alloy build`, peek at the generated
`.alloy/generated/stm32g071rb/peripherals.cpp` — you'll see
the DMA channels initialised before the UART, and the UART
TX / RX pointing at the channel handles instead of busy-loop
register accesses.

## Why double-buffer?

The HAL ships a circular double-buffered helper that lets the
firmware process half of the RX buffer while the DMA is
filling the other half.  That keeps the TX / RX paths
zero-copy at firmware-level granularity — no missed bytes
even at high baud rates with bursty traffic.

## What's next

You're ready to build your own peripherals.  Tips:

- The TUI `alloy ui` → press `a` to open the Peripheral Add
  screen with full IR-validated suggestions.
- AI agents can author the same flow via MCP — see
  [AI_INTEGRATION.md](../../AI_INTEGRATION.md).
- When in doubt, run `alloy doctor` — every issue type is
  catalogued in [ERROR_COOKBOOK.md](../../ERROR_COOKBOOK.md).
