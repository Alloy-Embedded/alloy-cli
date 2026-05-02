# Tasks — add-export-ci-toolchain-matrix

## Phase 1: Toolchain selector

- [x] 1.1 `core.export._toolchain_step(core: str) -> str`
      returns the YAML snippet for `arm-none-eabi-gcc`,
      `gcc-riscv64-unknown-elf`, or the Espressif Xtensa
      action based on the active core string.
- [x] 1.2 Unknown cores fall back to ARM (the safe default
      for STM32 / nRF / SAM / RP2040).  Heuristic matches
      device-name prefixes when the IR core string is
      unavailable.
- [x] 1.3 Unit tests cover the three branches plus the ARM
      fallback path.

## Phase 2: Workflow emitter

- [x] 2.1 `core.export.github_workflow(config)` emits a
      `profile: [debug, release]` matrix.
- [x] 2.2 Toolchain-install step inserted right after
      `setup-python`.
- [x] 2.3 `actions/cache@v4` keyed on
      `${{ hashFiles('alloy.toml', '.alloy/version.lock') }}`
      to short-circuit alloy-devices-yml downloads on warm
      runs.
- [x] 2.4 `actions/upload-artifact@v4` of `*.elf` + `*.map`
      with `retention-days: 14`.
- [x] 2.5 `alloy doctor --json` step gated by
      `if: failure()` so a broken job surfaces install hints.

## Phase 3: CLI surface

- [x] 3.1 `alloy export ci` lands at
      `.github/workflows/firmware.yml` (was
      `.github/workflows/build.yml`).
- [x] 3.2 `alloy export <kind> --dry-run` prints the YAML to
      stdout instead of writing files.

## Phase 4: Tests

- [x] 4.1 `tests/test_export_ci_toolchain_matrix.py`: 20
      cases covering the toolchain selector, the workflow
      emitter, and the new CLI behaviour.
- [x] 4.2 The emitted YAML parses through `yaml.safe_load`
      cleanly and exposes a `matrix.profile` array.
- [x] 4.3 CLI `--dry-run` prints to stdout without writing
      files.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [x] 5.2 `openspec validate add-export-ci-toolchain-matrix
      --strict` passes.
