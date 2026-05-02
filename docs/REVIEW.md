# `alloy-cli` review — what shipped, what's strong, what to improve

Snapshot taken after the 15-proposal roadmap closed (commits
`3a2f671..8592b3d`).  This is a working-doc audit of the codebase as
delivered, not a marketing summary.

## What shipped

Reproducible numbers from a clean checkout:

| Metric | Value |
|---|---|
| Source files | 69 Python modules |
| Source LOC | 10 203 |
| Tests | 30 modules / 310 cases / **all green** |
| Test LOC | 5 161 |
| OpenSpec changes archived | 15 / 15 |
| Specs published | 7 capabilities, 25 requirements |
| ruff / pyright | clean (`0 errors / 0 warnings / 0 informations`) |

Every spec scenario across every proposal has at least one test
asserting the contract.  Nothing was waived as "documentation
only".

## Documentation images

`scripts/generate_docs_images.py` emits SVG screenshots of every
TUI screen plus three CLI snippets into `docs/images/`:

| # | Surface | File |
|---|---------|------|
| 1 | Welcome screen | `01-welcome.svg` |
| 2 | Project Dashboard (5 panels) | `02-dashboard.svg` |
| 3 | Onboarding wizard | `03-onboarding.svg` |
| 4 | Board Picker | `04-board-picker.svg` |
| 5 | Peripheral Add (UART) | `05-peripheral-add.svg` |
| 6 | Clock Tree | `06-clock-tree.svg` |
| 7 | DMA Matrix | `07-dma-matrix.svg` |
| 8 | Memory Map | `08-memory-map.svg` |
| 9 | `alloy --help` | `09-cli-help.svg` |
| 10 | `alloy boards` | `10-cli-boards.svg` |
| 11 | `alloy doctor` | `11-cli-doctor.svg` |

Run `python scripts/generate_docs_images.py` to refresh.

## What's strong

* **IR grounding.**  Every pin / DMA / instance suggestion goes
  through `core.ir` lookups before it lands in a diff.  Hallucination
  defence in `tests/test_mcp_server.py::test_add_gpio_with_invalid_pin_returns_validation_summary`
  is the spec-pinned proof.
* **Three-façade discipline.**  CLI, TUI and MCP all delegate to the
  same `core.peripherals.add_*` operations.  Adding a new peripheral
  kind is one function + one Click subcommand + one MCP tool — the
  data flow is the same.
* **Deterministic output.**  `alloy.toml` and `src/peripherals.cpp`
  are emitted byte-for-byte stable; the round-trip tests in
  `test_project.py::test_write_is_deterministic_byte_for_byte` and
  `test_peripherals.py::test_emit_peripherals_cpp_is_deterministic`
  enforce that.
* **JSON contracts everywhere.**  `alloy boards --json`,
  `alloy devices --json`, `alloy doctor --json`, the MCP responses,
  and the bom export all agree on the same shape.  Every consumer
  (CI, opencode, Cursor) sees the same data.
* **Progress through MCP, not despite it.**  The opencode recipe
  + system prompt + alternate-client emitters mean the AI story is
  one `alloy chat` away on a fresh machine.  No model lock-in.
* **Strong test gating.**  Pilot-driven Textual tests, FakeRunner
  for subprocess work, lockfile round-trip, MCP subprocess smoke —
  every layer has a representative integration test.

## What's incomplete / weak

Ranked by impact.  Each item is something I'd schedule before a
public 0.1 release.

### P0 — beat the demo

1. **The pinout schematic mode is a rectangle.**  `PinoutWidget`
   renders a left-aligned ASCII frame today; CubeMX's quad-package
   visualisation is the killer feature we promised.  Per-package
   layout coordinates need to come from `alloy-devices-yml` (the
   PLL-block enrichment proposal in alloy-codegen would unblock
   this).
2. **No actual codegen integration.**  Every "alloy-codegen"
   reference is a TODO.  `core.build.run` runs cmake + ninja but
   never regenerates headers.  Until the alloy-codegen Python entry
   point stabilises, we're shipping a CMake bridge that consumes
   stale generated/ output.
3. **Build / Flash hardware-in-the-loop is missing.**  `core.build`
   and `core.flash` work end-to-end with the FakeRunner; nothing
   in CI exercises them against a real arm-none-eabi-gcc + probe-rs.
   First demo on real hardware will surface latent bugs (signal
   handling, environment passthrough, pty quirks).

### P1 — polish before the world sees it

4. **Direct-import binding pattern blocks injection.**  Several
   modules do `from alloy_cli.core.toolchain import detect_*`
   instead of `from alloy_cli.core import toolchain as _toolchain`.
   This forces the screenshot generator (and tests) to monkey-patch
   per-module copies of the binding.  We caught this one for
   `core.flash` / `core.build` already; `tui.screens.dashboard`
   still has it (the screenshot-stub layer monkey-patches it
   explicitly).  Audit the rest.
5. **Generic peripheral kinds are stubs.**  `add_generic` covers
   timer / pwm / adc / dac / can / dma / rtc / watchdog / qspi /
   sdmmc / usb / eth without per-kind validation.  The schema
   only validates the four typed kinds (uart / gpio / spi / i2c).
   A user can write a `[[peripherals]] kind = "timer"` with arbitrary
   payload and we'll happily round-trip it.
6. **DMA suggestion is half-wired.**  `core.suggestions.suggest_dma`
   exists, but `add_uart` doesn't call it (the `--dma` flag wires
   `dma=True` into the payload but never picks a default channel).
   Fix: when `dma=True` and `tx_dma`/`rx_dma` are absent, call
   `suggest_dma`.
7. **Clock tree edits don't persist.**  `ClockTreeScreen` gathers
   overrides into the widget but `Ctrl+S` is a stub notification —
   we never write back to `alloy.toml [clocks]`.  Persisting needs
   a small schema addition (named profiles map) plus a writer.
8. **DoctorScreen is missing.**  The CLI satisfies the spec, but
   `add-doctor-update-export` originally specified a TUI screen
   too.  Mounting the CLI table in a Textual `DataTable` is
   straightforward; we deferred it to keep proposal #15 small.
9. **`alloy update` is a lockfile rewrite.**  No actual pip / git
   submodule / SDK-download work happens.  The contract is right;
   the upgraders are stubs.  Wire each component to its real
   upgrade command behind `core.update.UPGRADERS`.
10. **CI export YAMLs don't install arm-gcc.**  `github_workflow`
    runs `alloy build` but the job has no toolchain matrix.  The
    workflow as-emitted will fail at link time on any non-trivial
    target.

### P2 — engineering hygiene

11. **`_emit_toml` is duplicated.**  `core.peripherals._emit_toml`
    mirrors `core.project.write` byte-for-byte using the now-public
    `emit_section` / `emit_peripheral`.  Refactor to expose
    `core.project.dumps(config) -> str` and share.
12. **Private-attr access in tests.**  Several tests use
    `registry._tools[name]` (MCP) and `global_registry._entries`
    (TUI registry).  Add public accessors (`get_tool`, `pop`).
13. **Some `# noqa: BLE001` survived earlier ruff cleanups.**
    The `_resolve_device_for` and `_load_context` paths catch
    bare `Exception` to avoid crashing the TUI on unexpected IR
    failures.  Convert to `AlloyCliError` re-raises with a
    structured fall-through.
14. **No CHANGELOG / RELEASE_NOTES.**  Once the first release
    cuts, downstream consumers need an authoritative version
    history.  Hatch-vcs gives us versions; we still need prose.
15. **No GitHub Actions wired in this repo.**  `.github/workflows/`
    has the matrix files committed but they were never executed
    because the repo isn't on GitHub yet.  First push will
    surface real CI lag.

### P3 — nice-to-have

16. **Snapshot test pinning.**  We have Pilot-driven assertions but
    no SVG goldens.  The artefacts in `docs/images/` are a
    natural starting point — wire `pytest-textual-snapshot` to
    diff against them.
17. **TUI accessibility audit.**  We honour `NO_COLOR` and `TERM=dumb`
    via `theme_path()`; we have not actually tested with a screen
    reader.  The glyph-only fallback covers state cues but the
    layout density may not.
18. **Performance: bulk device search.**  We dropped from
    minutes to ~7 seconds by reading `bulk-admitted/index.yml`.
    Caching the index in `.alloy/cache/` per submodule SHA would
    take that to <100 ms on subsequent invocations.
19. **`alloy debug` is a thin wrapper.**  No GDB UI; we just spawn
    the user's configured one.  Wiring a Textual GDB front-end
    alongside the existing screens is a future polish iteration.
20. **No telemetry / opt-in metrics.**  We have no idea which
    tools land for users.  Out of scope today — flagged so we
    don't forget.

## Roadmap suggestions for the next wave

Three OpenSpec changes that would close most of the P0-P1 list:

1. **`add-codegen-integration`** — wire `alloy_codegen.regenerate`
   into `core.build.run` once the codegen Python entry point
   stabilises in the alloy-codegen repo.  Closes 2 + 3 (when
   paired with hardware CI).
2. **`enrich-peripheral-kinds`** — extend `schema/alloy_toml_v1.json`
   to cover timer / pwm / adc / can / usb / eth; ship typed
   `add_<kind>` per peripheral.  Closes 5.
3. **`add-real-update-pipeline`** — implement
   `core.update.UPGRADERS = {"alloy": pip_upgrade, ...}` with
   atomic rollback on failure.  Closes 9.

The TUI side has its own follow-up:

4. **`add-tui-package-pinout`** — feed per-package perimeter
   coordinates from alloy-devices-yml into `PinoutWidget`'s
   schematic mode.  Closes 1.
5. **`add-tui-doctor-clock-persistence`** — DoctorScreen + clock
   profile persistence.  Closes 7 + 8.

Together those five proposals would land a 1.0-quality release
without changing the existing surface.
