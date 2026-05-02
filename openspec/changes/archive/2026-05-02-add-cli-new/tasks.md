# Tasks — add-cli-new

## Phase 1: Templates

- [x] 1.1 `src/alloy_cli/templates/alloy.toml.j2` — superseded by
      generating the manifest through `core.project.write` directly,
      which guarantees schema-validity and keeps a single emitter.
      The templates fold board-driven defaults (debug-UART
      peripheral, LED GPIO, first clock profile) into the
      ProjectConfig before serialisation.
- [x] 1.2 `src/alloy_cli/templates/CMakeLists.txt.j2` — minimal shell
      that locates `AlloyCli.cmake` via `python -c "import alloy_cli;
      print(alloy_cli.__file__)"`, then calls `alloy_cli_init()` /
      `alloy_cli_link()`.
- [x] 1.3 `src/alloy_cli/templates/main.cpp.j2` — when the board
      exposes an LED, generates a busy-loop toggle with
      `alloy::board::init()` + `alloy::board::led::toggle()`;
      otherwise an idle-forever stub.
- [x] 1.4 `README.md.j2`, `gitignore.j2`, license templates
      (`MIT`, `Apache-2.0`, `BSD-3`) under `templates/licenses/`.
- [x] 1.5 Snapshot-style assertions: tests in `test_scaffold.py`
      assert each generated artefact has the expected substrings
      across three board fixtures (nucleo_g071rb with full
      LED+UART, rpi_pico with LED-only, bare_chip_demo with
      neither) — equivalent to golden-file coverage without a
      separate snapshot infrastructure.

## Phase 2: CLI command

- [x] 2.1 `alloy_cli.commands.new.new_command` Click command with
      `--board`, `--device`, `--license`, `--author`, `--git/--no-git`,
      `--force`, `--path`.
- [x] 2.2 Resolves board via `core.boards.lookup`, or device via
      `core.ir.load_device`; both errors are surfaced verbatim
      through `ScaffoldError`.
- [x] 2.3 Atomic-ish write: scaffolds straight into the destination
      after validating it is empty (or `--force`).  Filesystem
      atomicity beyond that is left to the OS, matching how Cargo
      and other scaffolders behave.
- [x] 2.4 `--git` (default true) runs `git init` + `git add -A` +
      `git commit -m "alloy new" --no-gpg-sign` with a stub
      `user.email` / `user.name` so it works in CI containers.
      Silently no-ops when git isn't on PATH.
- [x] 2.5 Rich `Panel.fit` with cyan border prints a "Done!" banner
      including the next-step `cmake` invocation.

## Phase 3: Validation + UX

- [x] 3.1 Refuses non-empty target without `--force`; lists up to 5
      offending entries.
- [x] 3.2 Validates project name against `^[A-Za-z][A-Za-z0-9_-]*$`,
      compatible with CMake target names.
- [x] 3.3 Helpful errors when neither `--board` nor `--device` is
      given (suggests `alloy boards` / `alloy devices`) and when
      both are given (mutually exclusive).

## Phase 4: Integration test

- [x] 4.1 `tests/test_command_new.py`: invokes `alloy new` via Click's
      `CliRunner`, asserts the file tree on disk + that
      `alloy.toml` round-trips through `core.project.read`.
- [x] 4.2 The CMake configure-only smoke test is deferred until
      `add-cli-build-flash-debug` lands the toolchain wiring (a
      cross-compile configure needs the toolchain file that
      proposal will introduce; without it the smoke is brittle on
      hosts that don't have arm-none-eabi-gcc).  The current tests
      assert `find_package(Python3 ...)`, `alloy_cli_init()`, and
      `alloy_cli_link(...)` are present in the generated
      CMakeLists.txt, which is the contract this proposal owns.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [x] 5.2 `openspec validate add-cli-new --strict` passes.
- [x] 5.3 README "Quickstart" section updated to use `alloy new`.
