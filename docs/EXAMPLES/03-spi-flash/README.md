# 03 — SPI flash

Talks to a synthetic AT25-class SPI flash sitting on SPI1.
The driver shape is the same as a real SPI EEPROM/flash:
software CS, mode 0, MSB-first, 8-bit frames.

## Diff vs `02-uart-echo`

```diff
+[[peripherals]]
+kind = "spi"
+name = "flash_bus"
+peripheral = "SPI1"
+sck = "PA5"
+miso = "PA6"
+mosi = "PA7"
+mode = 0
+frame = 8
+prescaler = 4
+
+[[peripherals]]
+kind = "gpio"
+name = "flash_cs"
+pin = "PB6"
+mode = "output"
+initial = 1
+label = "AT25_nCS"
```

Two new peripherals:

1. The SPI bus itself (`flash_bus`) — note that `mode = 0`
   means CPOL=0 / CPHA=0, the canonical AT25 mode.
2. A separate GPIO (`flash_cs`) for software-controlled
   chip select.  The `initial = 1` keeps the line high
   (deasserted) at boot.

## Build + run

```bash
alloy new spi-flash --from-example 03-spi-flash
cd spi-flash
alloy build --profile debug
alloy flash
```

The example firmware reads the flash's JEDEC ID (opcode
`0x9F`) and prints it over the UART you wired in step 2.

## What's next

[04-dma-double-buffer](../04-dma-double-buffer/) wires DMA
into the UART RX path so the CPU stays free while bytes
stream in.
