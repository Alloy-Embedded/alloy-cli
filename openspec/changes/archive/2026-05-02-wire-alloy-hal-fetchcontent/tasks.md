# Tasks — wire-alloy-hal-fetchcontent

## Phase 1: Template

- [x] 1.1 `src/alloy_cli/templates/CMakeLists.txt.j2` rewritten
      with `include(FetchContent)`, `FetchContent_Declare(alloy
      ...)`, GIT_REPOSITORY + GIT_TAG, local override via
      `ALLOY_SOURCE_OVERRIDE`, and
      `FetchContent_MakeAvailable(alloy)`.
- [x] 1.2 The scaffold passes the board id down via
      `set(ALLOY_BOARD "${ALLOY_BOARD_ID}" CACHE STRING ""
      FORCE)` before MakeAvailable.
- [x] 1.3 `alloy_add_runtime_executable(${ALLOY_PROJECT_NAME}
      SOURCES src/main.cpp)` is the build target;
      `alloy_cli_link(${ALLOY_PROJECT_NAME})` continues to
      add the codegen include path.
- [x] 1.4 Chip-only projects (no `[board]`) raise
      `ScaffoldError` during scaffold pointing at a follow-up
      `wire-chip-only-projects` proposal.
- [x] 1.5 The CMakeLists template's AlloyCli.cmake lookup
      now tries the wheel layout first AND falls back to
      `<repo>/cmake/AlloyCli.cmake` so editable installs
      (`pip install -e .`) configure cleanly.

## Phase 2: AlloyCli.cmake

- [x] 2.1 `alloy_cli_link(target)` keeps adding the codegen
      include path and emits a one-shot warning when
      `Alloy::hal` is missing (consumer forgot to wire
      FetchContent).
- [x] 2.2 New `alloy_cli_resolve_alloy_tag(<output_var>)`
      reads `ALLOY_PROJECT_ALLOY` (set by `alloy_cli_init`
      from `alloy.toml [project].alloy`) and falls back to
      `main`.

## Phase 3: Tests

- [x] 3.1 `tests/test_scaffold_cmake_template.py` (10 cases):
      board-driven scaffold emits FetchContent_Declare(alloy,
      uses alloy_add_runtime_executable, passes ALLOY_BOARD
      through, supports ALLOY_SOURCE_OVERRIDE, calls
      `alloy_cli_resolve_alloy_tag`, keeps `alloy_cli_link`,
      and chip-only paths surface clean errors.  AlloyCli.cmake
      exposes the new resolve helper + warning.
- [x] 3.2 Existing `tests/test_scaffold.py` chip-only test
      migrated to assert the new ScaffoldError contract.
- [x] 3.3 The four `docs/EXAMPLES/*` continue to scaffold +
      parse via the existing
      `tests/test_quickstart_and_cookbook.py` round-trip.

## Phase 4: End-to-end smoke

- [x] 4.1 Verified locally:
      `alloy new e2e --board nucleo_g071rb` →
      `cmake -S . -B build -DALLOY_SOURCE_OVERRIDE=<alloy>
      -DCMAKE_BUILD_TYPE=Debug` configures clean.  alloy HAL
      pulls in (Selected device contract:
      st/stm32g0/stm32g071rb), Alloy::hal is created, the
      `e2e` target is wired against it.  Actual ARM compile
      requires `arm-none-eabi-gcc` on PATH (out of scope —
      the cross-toolchain story lives in alloy/).

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [x] 5.2 `openspec validate wire-alloy-hal-fetchcontent
      --strict` passes.
