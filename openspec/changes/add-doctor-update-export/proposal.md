# Add doctor + update + export Commands and Advanced TUI Views

## Why

Phase 5 closes adoption gaps that aren't blocking but dramatically
improve daily-driver UX.  Three CLI commands plus three TUI screens
that complete the catalogue defined in `docs/TUI_DESIGN.md`.

We bundle them because they share the same surface (diagnostics +
file emission + advanced visualisation) and ship together as the
"polish" wave.

## What Changes

### `alloy doctor` (CLI + TUI)

- CLI: deterministic JSON-or-table report of toolchains, probes,
  Python deps, project validity, network reachability, alloy
  version availability.
- TUI: `tui.screens.DoctorScreen` per `docs/TUI_DESIGN.md` Screen
  11.  Hotkeys: `r` re-run, `f` auto-fix safe issues.
- Auto-fix scope: install missing Python deps, init the
  alloy-devices-yml submodule.  Never auto-installs system
  toolchains (prints command, defers to user).

### `alloy update`

- Atomically upgrades one or more components: alloy, alloy-codegen,
  alloy-devices-yml, alloy-cli.
- Resolves new versions against `alloy.toml` ranges; updates
  `.alloy/version.lock`.
- `--dry-run` prints what would change without applying.
- `--frozen` mode forbids any change (CI bots).

### `alloy export <kind>`

Generates auxiliary configuration files from `alloy.toml`:

- `alloy export ci [--target github|gitlab|jenkins]` — CI
  workflow for the chosen platform.
- `alloy export vscode` — `.vscode/` directory: `launch.json`
  (cortex-debug + probe-rs settings), `tasks.json` (build /
  flash / debug shortcuts), `c_cpp_properties.json` (include
  paths).
- `alloy export gdb` — `.gdbinit` with probe-rs + project paths.
- `alloy export bom` — JSON bill-of-materials for the chip + any
  declared external components.

### TUI Advanced Views (`docs/TUI_DESIGN.md` Screens 5, 6)

- **`tui.screens.DmaMatrixScreen`** — peripheral × channel grid
  with bind / unbind interactions.  Reusable
  `tui.widgets.DmaMatrixWidget`.
- **`tui.screens.MemoryMapScreen`** — flash + RAM stacked-bar
  layout with section breakdown.  Reusable
  `tui.widgets.MemoryMapWidget`.

## Impact

After Phase 5, `alloy-cli` is a polished daily driver.  Newcomers
hit `alloy doctor` and resolve toolchain issues in one screen.
Power users get DMA + memory introspection.  CI/IDE integration is
one command away.

## What this DOES NOT do

- Web UI / browser target — defer.
- Multi-board project support — defer.
- Plugin system — defer.
- Custom build of vendor SDKs — never.
