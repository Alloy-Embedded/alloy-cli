# peripheral-operations Specification

## Purpose
TBD - created by archiving change add-cli-add-peripheral. Update Purpose after archive.
## Requirements
### Requirement: alloy-cli SHALL provide IR-validated peripheral wiring via `alloy add`

The `alloy add <kind>` command SHALL add a peripheral configuration
to the project's `alloy.toml` and `src/peripherals.cpp`, validating
**every** pin, DMA channel, clock, and rate against the canonical
device IR before producing a diff.  Validation failures SHALL prevent
the apply step.  Sensible defaults (lowest-numbered free instance,
first non-conflicting candidate pins, lowest free DMA channel) SHALL
be applied when CLI flags are omitted.

#### Scenario: alloy add uart succeeds with all defaults

- **WHEN** the user runs `alloy add uart --name app --apply` inside
  a project for `nucleo_g071rb` with no existing UART
- **THEN** the command SHALL exit 0
- **AND** `alloy.toml` SHALL gain a `[[peripherals]]` block with
  `kind="uart"`, `name="app"`, `peripheral="USART1"` (lowest free
  instance), `tx`/`rx` pins from `connection_candidates`
- **AND** `src/peripherals.cpp` SHALL contain a
  `alloy::Uart<board::USART1>` instantiation

#### Scenario: alloy add uart with invalid pin fails

- **WHEN** the user runs `alloy add uart --tx PA12 --rx PA13` and
  `connection_candidates[(PA12, USART1_TX)]` does not exist for
  the device
- **THEN** the command SHALL exit non-zero
- **AND** the diagnostic SHALL name PA12 and list valid alternatives
  for `USART1_TX` from the IR

#### Scenario: alloy add uart conflicting with existing peripheral fails

- **WHEN** USART2 already uses PA2/PA3 for debug
- **AND** the user runs `alloy add uart --peripheral USART2 --tx PA9`
- **THEN** the command SHALL exit non-zero with a Conflict
  diagnostic naming `peripherals[debug]` as the holder of USART2

#### Scenario: alloy add uart --diff-only does not write

- **WHEN** the user runs `alloy add uart --name app` with NO
  `--apply` flag
- **THEN** the command SHALL print a unified diff showing the
  proposed changes
- **AND** SHALL exit 0
- **AND** `alloy.toml` and `src/peripherals.cpp` SHALL NOT be
  modified

### Requirement: peripheral wiring SHALL re-emit src/peripherals.cpp deterministically

The generated `src/peripherals.cpp` SHALL be a deterministic
function of `alloy.toml [[peripherals]]`: re-running `alloy add`
on the same configuration twice SHALL produce byte-identical
output.  Comments emitted in the file SHALL include peripheral
name, alloy-cli version, and a "do not edit by hand" notice.

#### Scenario: peripherals.cpp is byte-stable across runs

- **WHEN** `alloy add gpio --pin PA5 --label LED --apply` is run
  twice in succession on the same project
- **THEN** the first run SHALL produce a non-empty diff
- **AND** the second run SHALL produce an empty diff
- **AND** the contents of `src/peripherals.cpp` SHALL be byte-
  identical in both states

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

### Requirement: alloy.toml SHALL be emitted by a single canonical writer

`core.project.dumps(config) -> str` SHALL be the only function
that turns a `ProjectConfig` into TOML text.  `core.project.write`
SHALL delegate to `dumps`; the diff path in `core.peripherals`
SHALL consume `dumps` instead of duplicating the emit logic.
The previous `core.peripherals._emit_toml` SHALL be deleted.

#### Scenario: dumps round-trips through read

- **WHEN** a `ProjectConfig` is serialised via
  `core.project.dumps(config)`
- **AND** the result is parsed back via `core.project.read`
- **THEN** the resulting `ProjectConfig` SHALL be byte-identical
  on a second `dumps` pass
- **AND** the diff path in `core.peripherals.add_*` SHALL render
  identical before / after text whether it builds the strings
  via `dumps` or via the old internal helper

