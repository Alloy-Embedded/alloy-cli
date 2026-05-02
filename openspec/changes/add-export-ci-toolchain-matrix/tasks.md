# Tasks — add-export-ci-toolchain-matrix

## Phase 1: Toolchain selector

- [ ] 1.1 `core.export._toolchain_step(core: str) -> str`
      returns the YAML snippet for `arm-none-eabi-gcc`,
      `riscv-gnu-toolchain`, or `xtensa-esp32-elf` based on
      `DeviceIR.identity.core`.
- [ ] 1.2 Unknown cores fall back to a commented placeholder +
      a warning emitted to stderr at export time.
- [ ] 1.3 Unit tests cover every supported core string.

## Phase 2: Workflow emitter

- [ ] 2.1 Rewrite `core.export.github_workflow(config, ir)` to
      produce a matrix on `profile ∈ {debug, release}`.
- [ ] 2.2 Insert the toolchain-install step right after
      `setup-python`.
- [ ] 2.3 Wire `astral-sh/setup-uv@v3` + `uv sync` for the
      Python dev environment.
- [ ] 2.4 `actions/cache@v4` keyed on
      `${{ hashFiles('alloy.toml', '.alloy/version.lock') }}`.
- [ ] 2.5 `actions/upload-artifact@v4` of `*.elf` + `*.map`
      with `retention-days: 14`.
- [ ] 2.6 Append a `alloy doctor --json` step gated by
      `if: failure()`.

## Phase 3: CLI surface

- [ ] 3.1 `alloy export ci` keeps its current signature; the
      output now lands at `.github/workflows/firmware.yml` by
      default, overrideable via `--out`.
- [ ] 3.2 `alloy export ci --dry-run` prints the YAML to
      stdout instead of writing to disk.

## Phase 4: Tests

- [ ] 4.1 Snapshot test of the emitted YAML for an STM32G0
      chip target.
- [ ] 4.2 Snapshot test for an RP2040 chip target (RISC-V
      flavour).
- [ ] 4.3 `actionlint` (or pyyaml + a small schema check) runs
      against the emitted YAML in the test suite to catch
      malformed steps.
- [ ] 4.4 Round-trip: `alloy export ci --dry-run | yamllint
      -` exits zero on a fresh project.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/cli-surface/spec.md`.
- [ ] 5.2 `openspec validate add-export-ci-toolchain-matrix
      --strict` passes.
- [ ] 5.3 `docs/AI_INTEGRATION.md` mentions `alloy export ci`
      as the recommended bootstrap step in the LLM cookbook —
      lands in a follow-up doc-only PR.
