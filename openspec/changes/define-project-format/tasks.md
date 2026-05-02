# Tasks — define-project-format

## Phase 1: Schema

- [ ] 1.1 `schema/alloy_toml_v1.json` — JSON Schema (Draft 2020-12)
      defining `[project]`, `[board]` / `[chip]`, `[clocks]`,
      `[[peripherals]]`, `[build]`, `[flash]`.
- [ ] 1.2 Per-peripheral kind sub-schemas: uart, gpio, spi, i2c,
      tim, pwm, adc, dac, can, dma, rtc, watchdog, qspi, sdmmc,
      usb, eth.
- [ ] 1.3 Schema doc at `docs/PROJECT_FORMAT.md` (user-facing).

## Phase 2: Parser + writer

- [ ] 2.1 `core.project.ProjectConfig` dataclass.
- [ ] 2.2 `core.project.read(path) -> ProjectConfig` using `tomli`,
      validates against the JSON Schema.
- [ ] 2.3 `core.project.write(config, path)` using `tomlkit` to
      preserve user comments, deterministic key order.
- [ ] 2.4 Migration framework: `core.project.migrate(toml_text,
      from_version, to_version)`.

## Phase 3: `.alloy/` cache

- [ ] 3.1 `core.project.AlloyDir(repo_root)` provides paths:
      `version.lock`, `cache/`, `generated/`.
- [ ] 3.2 Auto-create on first write; idempotent.

## Phase 4: CMake bridge

- [ ] 4.1 `cmake/AlloyCli.cmake` with a single `alloy_cli_init()`
      function.
- [ ] 4.2 `alloy_cli_init()` shells out to `python -m
      alloy_cli.cmake_bridge --emit-json` to get a manifest JSON
      and read it via `cmake_file(READ)` + `string(JSON ...)`.
- [ ] 4.3 `alloy_cli_link(target)` adds the right include paths and
      linker flags.

## Phase 5: Tests

- [ ] 5.1 Round-trip test: write a `ProjectConfig`, read it back,
      compare structurally.
- [ ] 5.2 Schema validation negative tests (10 invalid `alloy.toml`
      fixtures, each with a distinct violation).
- [ ] 5.3 CMake bridge integration test: synthetic fixture project
      → `cmake -B build` succeeds, build is not run.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/project-format/spec.md`.
- [ ] 6.2 `openspec validate define-project-format --strict` passes.
- [ ] 6.3 `pyright --strict src/alloy_cli/core/project.py` passes.
