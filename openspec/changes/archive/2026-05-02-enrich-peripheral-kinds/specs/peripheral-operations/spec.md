## ADDED Requirements

### Requirement: alloy-cli SHALL provide IR-validated wiring for timer / pwm / adc / dac / can / usb / eth

`core.peripherals` SHALL ship typed `add_timer`, `add_pwm`,
`add_adc`, `add_dac`, `add_can`, `add_usb`, and `add_eth`
operations.  Each SHALL validate its pin / channel inputs against
`core.ir.connection_candidates` and the device's peripheral list,
SHALL apply the same lowest-numbered-free-instance default as the
existing kinds, and SHALL produce an `AddResult` with the same
shape as today's `add_uart` / `add_gpio` / `add_spi` / `add_i2c`.
Click subcommands and MCP tools matching each operation SHALL
land alongside the core function.

#### Scenario: alloy add pwm rejects a pin not in the IR's connection candidates

- **WHEN** the user runs `alloy add pwm --name fan --peripheral
  TIM2 --channel 1 --pin PA12`
- **AND** the device IR has no `connection_candidates[(PA12, TIM2_CH1)]`
- **THEN** the command SHALL exit non-zero
- **AND** the diagnostic SHALL include `code="invalid-pin"` and a
  suggestions list of legal pins for `TIM2_CH1`

#### Scenario: alloy add can defaults TX/RX pins from the IR

- **WHEN** the user runs `alloy add can --name powertrain --bitrate 500000`
- **AND** the device IR exposes a `CAN1` peripheral with
  `connection_candidates[CAN1.TX]` and `[CAN1.RX]`
- **THEN** the diff SHALL pin the lowest-numbered IR-valid TX +
  RX pair into the payload
- **AND** the validation panel SHALL be empty of error-severity
  diagnostics

#### Scenario: alloy add usb mode is enum-validated against {device, host, otg}

- **WHEN** the user runs `alloy add usb --name dev --mode peripheral`
- **THEN** the schema validator SHALL reject `mode="peripheral"`
- **AND** the message SHALL list `device, host, otg` as the
  legal values

### Requirement: --dma SHALL auto-select a DMA channel when no override is given

`core.suggestions.suggest_dma_pair` SHALL return a `DmaPair { tx,
rx }` for any peripheral instance that the IR exposes DMA routes
for, honouring channels already claimed by other peripherals.
`add_uart`, `add_spi`, and `add_i2c` SHALL call it whenever
`--dma` is set and no explicit `--tx-dma` / `--rx-dma` overrides
are provided.  The chosen channels SHALL appear in both the
written `alloy.toml` and the emitted `peripherals.cpp`.

#### Scenario: alloy add uart --dma fills tx_dma + rx_dma automatically

- **WHEN** the user runs `alloy add uart --name console --dma`
- **AND** the device IR's `dma_routes` exposes free channels for
  the chosen USART instance (TX + RX directions)
- **THEN** the resulting `[[peripherals]]` entry SHALL include
  `tx_dma` and `rx_dma` with concrete channel ids
- **AND** the regenerated `src/peripherals.cpp` SHALL reference
  both channels in the DMA-enabled UART instantiation

#### Scenario: --dma without free channels surfaces a typed diagnostic

- **WHEN** every DMA channel for a UART's TX direction is already
  claimed by an existing peripheral
- **AND** the user runs `alloy add uart --name extra --dma`
- **THEN** the diagnostic SHALL be `code="no-dma-channels"`
- **AND** the diff SHALL NOT be cached / applied
