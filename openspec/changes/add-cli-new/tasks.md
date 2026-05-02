# Tasks — add-cli-new

## Phase 1: Templates

- [ ] 1.1 `src/alloy_cli/templates/alloy.toml.j2` — pre-populates
      board / clocks / one starter peripheral (debug UART when
      board provides it).
- [ ] 1.2 `src/alloy_cli/templates/CMakeLists.txt.j2` — minimal
      shell calling `alloy_cli_init()` + `add_executable` +
      `alloy_cli_link()`.
- [ ] 1.3 `src/alloy_cli/templates/src/main.cpp.j2` —
      `board::init()` + a `while (true)` busy loop calling
      `board::led::toggle()` (when board has LED) or empty.
- [ ] 1.4 `README.md.j2`, `.gitignore.j2`, license templates.
- [ ] 1.5 Unit tests with golden-file snapshots for each template
      against 3 board fixtures (nucleo_g071rb, pico, esp32-c3).

## Phase 2: CLI command

- [ ] 2.1 `alloy_cli.cli.new` Click command with `--board`,
      `--device`, `--license`, `--git/--no-git`, `--force`.
- [ ] 2.2 Resolves board → `BoardManifest`; or device →
      `DeviceIR.identity`.
- [ ] 2.3 Generates project tree atomically (write to `tempdir`
      then `os.replace`).
- [ ] 2.4 If `--git` (default), runs `git init` + `git add` + `git
      commit -m "alloy new"`.
- [ ] 2.5 Prints "Done!  cd <name>; alloy build" with rich
      formatting.

## Phase 3: Validation + UX

- [ ] 3.1 Refuses non-empty target directory without `--force`.
- [ ] 3.2 Validates project name (must be a valid CMake target).
- [ ] 3.3 Helpful error when neither `--board` nor `--device` is
      given (suggest `alloy boards` and `alloy devices`).

## Phase 4: Integration test

- [ ] 4.1 `tests/integration/test_new.py`: scaffold into tempdir,
      assert structure, assert `alloy.toml` validates against the
      schema.
- [ ] 4.2 Smoke: run `cmake -B build` inside the scaffolded
      directory; expect success (build is not run).

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [ ] 5.2 `openspec validate add-cli-new --strict` passes.
- [ ] 5.3 README "Quickstart" section updated to use `alloy new`.
