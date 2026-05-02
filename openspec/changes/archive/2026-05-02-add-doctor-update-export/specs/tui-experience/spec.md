## ADDED Requirements

### Requirement: alloy-cli SHALL provide TUI screens for DMA matrix and memory map

The `DmaMatrixScreen` SHALL render a peripheral × channel grid
with the existing bindings highlighted, conflict cells flagged,
and inline bind / unbind interactions.  The `MemoryMapScreen`
SHALL render flash and RAM regions as stacked-bar visualisations
driven by IR `memories[]` plus the last `.elf` map file, with a
per-section breakdown panel.

#### Scenario: DMA matrix displays current bindings

- **WHEN** the user opens `tui.screens.DmaMatrixScreen` on a
  project with `USART1_TX → DMA1_CH1` and `USART1_RX → DMA1_CH2`
- **THEN** the matrix cell at row USART1_TX × column ch1 SHALL
  show ● (bound)
- **AND** the cell at row USART1_RX × column ch2 SHALL show ●
- **AND** all other cells SHALL show ◯ (available) or be empty
  for incompatible (peripheral, channel) pairs

#### Scenario: Memory map reports flash usage

- **WHEN** the user opens `tui.screens.MemoryMapScreen` after a
  successful build that produced a 32 KB ELF on a 128 KB device
- **THEN** the flash bar SHALL show 25% used
- **AND** the section breakdown SHALL list `.text`, `.rodata`,
  `.data`, `.bss` sizes from the linker `.map` file
