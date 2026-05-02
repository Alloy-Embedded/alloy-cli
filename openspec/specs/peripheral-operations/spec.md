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

