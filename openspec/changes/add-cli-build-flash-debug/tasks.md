# Tasks — add-cli-build-flash-debug

## Phase 1: Build orchestration

- [ ] 1.1 `core.build.run(profile, clean) -> BuildResult` —
      orchestrates codegen → cmake → ninja.
- [ ] 1.2 `core.codegen.regenerate_if_stale(device, out_dir)` —
      checks `.alloy/generated/<device>/.stamp` against IR sha +
      alloy-codegen version; invokes `alloy-codegen generate` only
      when needed.
- [ ] 1.3 `core.memory.parse_elf(path) -> MemoryReport` — uses
      `arm-none-eabi-size` (or equivalent) for flash/RAM totals and
      parses the linker `.map` file for per-section breakdown.
- [ ] 1.4 `cli.build` Click command wiring all of the above.
- [ ] 1.5 Streams output via `rich.console` with phase headers.

## Phase 2: Flash

- [ ] 2.1 `core.flash.detect_probes() -> tuple[ProbeInfo, ...]` via
      `probe-rs list --output json`.
- [ ] 2.2 `core.flash.run(probe, elf, target?) -> FlashResult` —
      invokes `probe-rs run` with progress callback.
- [ ] 2.3 OpenOCD fallback path (configurable per board via
      `alloy.toml [flash].openocd_config`).
- [ ] 2.4 `cli.flash` Click command.

## Phase 3: Debug

- [ ] 3.1 `core.debug.start(probe, elf) -> DebugSession` —
      launches probe-rs gdb-server, returns the TCP port and
      target ELF.
- [ ] 3.2 GDB front-end resolution: explicit `--gdb-ui`, env
      `ALLOY_GDB`, fallback to plain `arm-none-eabi-gdb`.
- [ ] 3.3 `cli.debug` spawns gdb attached to the server, forwards
      stdin/stdout, cleans up gdb-server on exit.

## Phase 4: Toolchain hardening

- [ ] 4.1 Cache toolchain detection results in
      `.alloy/cache/toolchain.json` per session (revalidate on
      version change).
- [ ] 4.2 Helpful error when arm-gcc is missing — print install
      command + link to `alloy doctor`.

## Phase 5: Integration tests

- [ ] 5.1 Smoke against the `nucleo_g071rb` template scaffold:
      `alloy new` → `alloy build` produces a non-empty `.elf`.
- [ ] 5.2 Mocked `probe-rs` integration test for `alloy flash`
      (no hardware needed).

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/cli-surface/spec.md`.
- [ ] 6.2 `openspec validate add-cli-build-flash-debug --strict`
      passes.
- [ ] 6.3 README "Quickstart" updated with the four commands.
