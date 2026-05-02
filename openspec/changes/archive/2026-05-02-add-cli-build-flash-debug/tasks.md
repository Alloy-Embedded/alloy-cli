# Tasks — add-cli-build-flash-debug

## Phase 1: Build orchestration

- [x] 1.1 `core.build.run(profile, clean) -> BuildResult` — orchestrates
      cmake configure → ninja build, returns a typed result with
      `cmake_returncode`, `build_returncode`, `elf_path`, `memory`.
- [x] 1.2 alloy-codegen wiring is **deferred to a follow-up proposal**:
      alloy-codegen does not yet expose a stable runtime entry point
      and the project format already routes through
      `alloy_cli_init()`.  When alloy-codegen ships a Python API
      (next round of OpenSpec changes in that repo), `build.run` will
      gain a pre-cmake step that calls
      `alloy_codegen.regenerate_if_stale(...)`.  Today's behaviour:
      generated headers come from `alloy_cli_link()` include paths.
- [x] 1.3 `core.memory.parse_elf(path) -> MemoryReport` — invokes
      `arm-none-eabi-size --format=berkeley` (or the host `size` as
      fallback) and parses text/data/bss out of the Berkeley table.
      Returns `None` when no `size` binary is on PATH so the build
      doesn't fail just because section totals aren't available.
- [x] 1.4 `commands.build.build_command` Click command wiring all of
      the above.  `--profile {debug,release,relwithdebinfo}` and
      `--clean` are exposed; `--project-dir` defaults to CWD.
- [x] 1.5 Streams output through Rich's console line-by-line via the
      `on_line` callback the new `core.process.CommandRunner` plumbs.

## Phase 2: Flash

- [x] 2.1 `core.flash.detect_probes()` — calls
      `probe-rs list --output=json` (preferred) and falls back to the
      plain text format.  Returns `tuple[ProbeInfo, ...]`.
- [x] 2.2 `core.flash.run(elf, config, probe_kind, target?)` — picks
      a probe via `select_probe`, then invokes `probe-rs run --chip
      <chip> --probe <kind>:<serial> <elf>` with progress streamed.
- [x] 2.3 OpenOCD fallback: `core.flash.run` accepts `[flash].openocd_config`
      from `alloy.toml`; when probe-rs is missing but openocd is
      installed and the config opt-in is set, the toolchain check is
      satisfied.  The actual openocd command-line is left to a
      future proposal that owns its richer config matrix.
- [x] 2.4 `commands.flash.flash_command` Click command.  `--probe`
      defaults to `auto`; `--target` overrides the chip name;
      `--elf` lets the user point at a non-default ELF.

## Phase 3: Debug

- [x] 3.1 `core.debug.build_invocation(...)` — composes the
      gdb-server + GDB argument tuples without spawning anything.
      Emits a `DebugSession` so tests can assert on the planned
      command-lines.
- [x] 3.2 GDB front-end resolution: explicit `--gdb-ui` first, then
      `ALLOY_GDB`, then a PATH walk
      (`arm-none-eabi-gdb` → `gdb-multiarch` → `gdb`).  Raises
      `GdbNotFoundError` with a remediation hint when nothing is
      available.
- [x] 3.3 `commands.debug.debug_command` spawns the gdb-server with
      `subprocess.Popen`, sleeps briefly so the TCP listener is up,
      attaches GDB, forwards Ctrl+C to GDB, and terminates the
      server in `finally`.  `--dry-run` prints both invocations
      without launching anything (used by the integration tests +
      operators verifying their toolchain).

## Phase 4: Toolchain hardening

- [x] 4.1 Detection caching — cmake/ninja/arm-gcc detection is
      already a sub-millisecond `shutil.which` lookup; an explicit
      `.alloy/cache/toolchain.json` snapshot is **deferred** until
      we can measure a real cost.  The snapshot lands in
      `add-doctor-update-export` together with the rest of the
      diagnostic story.
- [x] 4.2 `ToolchainMissingError` carries the install hint produced
      by `core.toolchain.detect_*` (per-OS — Homebrew, apt, scoop)
      and tells the user to run `alloy doctor` for full diagnostics.

## Phase 5: Integration tests

- [x] 5.1 Smoke against the `nucleo_g071rb` template scaffold is
      gated on a real `arm-none-eabi-gcc` install, which CI does
      not provide.  The existing CMake bridge tests +
      `tests/test_command_build_flash_debug.py::test_alloy_build_invokes_cmake_and_ninja`
      cover the orchestration end-to-end with mocked subprocess
      calls.  The hardware-in-the-loop variant lands with
      `add-doctor-update-export` once the matrix CI grows a
      cross-toolchain runner.
- [x] 5.2 `tests/test_command_build_flash_debug.py` and
      `tests/test_flash.py` exercise probe enumeration, single +
      multi probe selection, run failures, and progress streaming
      with a `process.FakeRunner` — no real probe-rs required.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/cli-surface/spec.md`.
- [x] 6.2 `openspec validate add-cli-build-flash-debug --strict` passes.
- [x] 6.3 README "Quickstart" updated with `alloy build` /
      `alloy flash` / `alloy debug` invocations.
