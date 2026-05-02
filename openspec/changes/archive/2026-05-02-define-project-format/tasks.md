# Tasks — define-project-format

## Phase 1: Schema

- [x] 1.1 `schema/alloy_toml_v1.json` — JSON Schema (Draft 2020-12)
      defining `[project]`, `[board]` / `[chip]`, `[clocks]`,
      `[[peripherals]]`, `[build]`, `[flash]`.
- [x] 1.2 Per-peripheral kind sub-schemas: uart, gpio, spi, i2c,
      tim, pwm, adc, dac, can, dma, rtc, watchdog, qspi, sdmmc,
      usb, eth.
- [x] 1.3 Schema doc at `docs/PROJECT_FORMAT.md` (user-facing).

## Phase 2: Parser + writer

- [x] 2.1 `core.project.ProjectConfig` dataclass.
- [x] 2.2 `core.project.read(path) -> ProjectConfig` using `tomllib`,
      validates against the JSON Schema.
- [x] 2.3 `core.project.write(config, path)` — deterministic emitter
      (stable key order, peripheral kind/name first).  Note:
      switched from tomlkit to a small in-house emitter to keep the
      dependency surface tight; comment-preservation is deferred to
      a later proposal once the TUI starts editing live files.
- [x] 2.4 Migration framework: schema_version field is enforced;
      `core.project._check_schema_version` rejects major != 1 with
      `ProjectConfigVersionError`.  A future proposal will add the
      actual `migrate()` helper when the first v2 lands.

## Phase 3: `.alloy/` cache

- [x] 3.1 `core.project.AlloyDir(repo_root)` provides paths:
      `version.lock`, `cache/`, `generated/`.
- [x] 3.2 `AlloyDir.ensure()` creates the layout idempotently.

## Phase 4: CMake bridge

- [x] 4.1 `cmake/AlloyCli.cmake` with `alloy_cli_init()` +
      `alloy_cli_link()` functions.
- [x] 4.2 `alloy_cli_init()` shells out to `python -m
      alloy_cli.cmake_bridge --emit-json` and parses the manifest
      via CMake's built-in `string(JSON ...)`.
- [x] 4.3 `alloy_cli_link(target)` adds the `.alloy/generated/include`
      directory to the target's include path (linker flags will land
      with alloy-codegen integration in a later proposal).

## Phase 5: Tests

- [x] 5.1 Round-trip test: write a `ProjectConfig`, read it back,
      compare structurally (`test_write_then_read_roundtrip_preserves_structure`).
- [x] 5.2 Schema validation negative tests — 11 invalid `alloy.toml`
      shapes covering missing fields, unknown peripheral kinds,
      invalid enum values, mutually exclusive `[board]`/`[chip]`,
      malformed schema_version.
- [x] 5.3 `cmake_bridge` integration tests: JSON manifest emission,
      pretty-printing, missing `alloy.toml` exits 2, sorted-key
      stability.  (CMake configure-only smoke test deferred — needs
      a synthetic toolchain file and is more naturally covered when
      `add-cli-new` ships generated `CMakeLists.txt` templates.)

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/project-format/spec.md`.
- [x] 6.2 `openspec validate define-project-format --strict` passes.
- [x] 6.3 `pyright src tests` reports 0 errors / 0 warnings.
      (Strict-mode hardening is tracked under a dedicated future
      proposal — the codebase is currently on basic mode.)
