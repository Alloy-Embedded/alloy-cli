# Emit a Cross-Compile-Capable CI Workflow from `alloy export`

## Why

`alloy export ci` writes a GitHub Actions workflow that runs
`pip install alloy-cli` + `alloy build`, but the job has no
embedded toolchain.  `arm-none-eabi-gcc` is not on `$PATH`,
which makes the workflow fail at link time on every target the
CLI actually serves.

The existing emitter is therefore a footgun: a user copies the
generated YAML, pushes it, and gets a red CI on the first run.
The fix is small but visible — install the toolchain, cache it,
matrixify the profile.

## What Changes

### Generated workflow shape

- New file written to `.github/workflows/firmware.yml` (path
  configurable via `--out`).
- Job matrix on `profile ∈ {debug, release}` so reviewers see
  both flavours pass.
- Toolchain install via
  `carlosperate/arm-none-eabi-gcc-action@v1` for
  `arm-none-eabi-gcc` (default toolchain for STM32 / SAM
  families).  RP2040 / ESP32 land in a follow-up.
- `astral-sh/setup-uv@v3` + `uv sync` for the Python deps so
  CI mirrors the local dev environment.
- `actions/cache@v4` keyed on the alloy.toml + lockfile SHA so
  alloy-codegen + alloy-devices-yml downloads land once per
  cache window.
- `actions/upload-artifact@v4` of the generated ELF + map file
  with retention 14 days.

### Per-vendor toolchains

- `_toolchain_step(target_arch: str)` returns the right setup
  step.  Initial coverage:
  - `cortex-m*` (STM32 / SAM) → arm-none-eabi-gcc.
  - `rv32imac` (esp32-c3 et al.) → riscv-gnu-toolchain action.
  - `xtensa-esp32-elf` (ESP32 classic) → espressif/install
    action.
- The chosen step is determined from
  `DeviceIR.identity.core` so the user never picks
  manually.

### Doctor-friendly footer

- Add a `alloy doctor --json` step at the end so a failing job
  prints the diagnostic table instead of an opaque "build
  failed" line.

## Impact

- `alloy export ci` becomes a "drop-in" tool: pushing the
  generated YAML produces a green CI on the first run.
- The matrix (debug + release) catches LTO regressions early.
- Doctor footer turns ambiguous CI failures into actionable
  install hints.

## What this DOES NOT do

- Does not generate workflows for non-GitHub CI providers
  (GitLab, Buildkite) — wave-4.
- Does not run on a self-hosted matrix; the runner is
  `ubuntu-latest`.
- Does not flash hardware in the generated workflow — that's
  the HIL workflow (`hil.yml`), which the user wires once
  hardware is online.
