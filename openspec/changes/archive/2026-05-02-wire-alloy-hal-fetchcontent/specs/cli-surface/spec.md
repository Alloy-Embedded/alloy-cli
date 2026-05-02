## ADDED Requirements

### Requirement: Scaffolded CMakeLists SHALL FetchContent the alloy HAL by default

The CMakeLists template emitted by `alloy new` SHALL pull the
alloy C++ HAL via `FetchContent_Declare(alloy ...)` and call
the HAL's `alloy_add_runtime_executable(...)` helper to link
the produced binary against `Alloy::hal`.  The version pinned
in `alloy.toml [project].alloy` SHALL flow through to the
HAL's GIT_TAG; missing pins fall back to `main`.  A
`-DALLOY_SOURCE_OVERRIDE=<path>` cache variable SHALL bypass
the git fetch and consume a local HAL checkout, so contributors
working on the HAL alongside a downstream project don't pay the
network round-trip.

#### Scenario: a board-driven project configures with the HAL pulled in

- **WHEN** the user runs `alloy new myproj --board
  nucleo_g071rb` and the resulting `CMakeLists.txt` is read
- **THEN** the file SHALL contain
  `FetchContent_Declare(alloy` and
  `alloy_add_runtime_executable(`
- **AND** SHALL `set(ALLOY_BOARD "${ALLOY_BOARD_ID}" CACHE
  STRING "" FORCE)` before `FetchContent_MakeAvailable(alloy)`
  so alloy resolves the platform / linker for the board

#### Scenario: a chip-only project errors with a clear message

- **WHEN** the user runs `alloy new chipproj --device
  st/stm32g0/stm32g071rb`
- **THEN** the scaffold SHALL exit non-zero with a message
  pointing at the chip-only-board follow-up proposal
- **AND** SHALL NOT leave a half-written project tree on disk

#### Scenario: ALLOY_SOURCE_OVERRIDE bypasses the git fetch

- **WHEN** the user runs `cmake -S . -B build
  -DALLOY_SOURCE_OVERRIDE=/path/to/alloy
  -DALLOY_BOARD=nucleo_g071rb`
- **THEN** the configure pass SHALL NOT issue a git fetch
- **AND** SHALL include the HAL via
  `FetchContent_Declare(alloy SOURCE_DIR
  /path/to/alloy)`
