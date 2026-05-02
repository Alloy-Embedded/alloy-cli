# Add `alloy new` Command

## Why

`alloy new` is the user's first contact with `alloy-cli`.  It must
turn `alloy new my-firmware --board nucleo_g071rb` into a working
project that compiles and flashes — in under 5 seconds, without
asking the user to write a single line of CMake.

This proposal ports the scaffolder logic from
`alloy/tools/alloy-cli/scaffold.py` and the Jinja2 templates from
`alloy/tools/alloy-cli/_templates/` into this repo, then upgrades
them to produce an `alloy.toml`-shaped project.

## What Changes

- **`alloy new <NAME> [--board ID] [--device VENDOR/FAMILY/CHIP]
  [--license MIT|APACHE-2.0|BSD-3] [--git/--no-git]`** — the new
  CLI entry.
- **Templates** under `src/alloy_cli/templates/` (Jinja2):
  - `alloy.toml.j2` — schema-v1 manifest pre-populated for the
    chosen board/chip
  - `CMakeLists.txt.j2` — minimal, calls `alloy_cli_init()` from
    Phase 1
  - `src/main.cpp.j2` — empty `int main()` with the chosen board's
    `board::init()`
  - `README.md.j2`
  - `.gitignore.j2`
- **Board-driven defaults**: when `--board` is given, copy
  `clocks.profile`, debug-UART peripheral, LED GPIO definition into
  `alloy.toml` so the user gets a working starting point.
- **Chip-only mode**: `--device st/stm32g0/stm32g071rb` works
  without a board manifest; the user gets a chip-only project with
  no LED / debug-UART defaults.
- **Validation**: refuses to scaffold into a non-empty directory
  unless `--force`.

## Impact

- New users get working firmware with one command, like Cargo.
- Inside any scaffolded project, `alloy build` (Phase 2) +
  `alloy flash` (Phase 2) Just Work.
- Templates are tested via snapshot fixtures (golden file
  comparison after rendering).

## What this DOES NOT do

- No interactive board picker yet — that's the TUI in
  `add-tui-board-picker` (Phase 3).  Without `--board` /
  `--device`, this command exits with an error pointing at
  `alloy boards` (next proposal).
- No "starter peripheral" prompts — that's the onboarding wizard
  in Phase 3.
- No multi-board project generation.
