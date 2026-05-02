# Define Project Format

## Why

`alloy-cli` operates on user firmware projects.  Every command —
`alloy add`, `alloy build`, `alloy flash` — needs a single source
of truth for "what is this project".  The de-facto standard
elsewhere is fragmented: PlatformIO has `platformio.ini`,
Modm has Python scripts, Cargo has `Cargo.toml`, west has its own
manifest format, Zephyr is Devicetree.

We pick **TOML** for human-readable, easy-to-parse configuration —
matches Cargo's ergonomics — and pin a clear schema.  The format
must support: project metadata, board / chip selection, clock
profile, peripherals (UART / GPIO / SPI / I²C / TIM / PWM / ADC /
DMA / etc.), build options, flash configuration.

## What Changes

- **`alloy.toml` schema v1.0.0** — top-level keys: `[project]`,
  `[board]` *or* `[chip]`, `[clocks]`, `[[peripherals]]` (one per
  peripheral), `[build]`, `[flash]`.
- **JSON Schema** at `schema/alloy_toml_v1.json` to validate the
  format; carried inside the `alloy_cli` package as a data file.
- **`core.project.read(path)`**: parses + validates `alloy.toml`,
  returns a typed `ProjectConfig` dataclass.
- **`core.project.write(config, path)`**: deterministic round-trip
  serialisation (stable key order, comments preserved via tomlkit).
- **`.alloy/` cache layout**: `version.lock`, `cache/`, `generated/`.
- **CMake helper** (`cmake/AlloyCli.cmake`) that reads `alloy.toml`
  via a Python sidecar invocation and emits a JSON manifest CMake
  consumes.  This is the integration point used by every project's
  generated `CMakeLists.txt`.
- **`alloy.toml` migration story**: schema_version field + a
  `core.project.migrate(...)` helper for future bumps.

## Impact

- Every Phase-2 CLI command operates on `ProjectConfig` instead of
  ad-hoc parsing.
- Schema-validated; bad configs surface with clear errors at config
  time, not at compile time.
- TUI screens later edit a `ProjectConfig` and round-trip through
  `core.project.write` — no string-fiddling.

## What this DOES NOT do

- Does not implement any `alloy add` operations.  Those are in
  `add-cli-add-peripheral`.
- Does not generate CMake source (the helper just reads the TOML).
- Does not handle multi-board projects.
- Does not version-pin alloy/alloy-codegen/alloy-devices-yml — that
  is handled by `core.lockfile` from `integrate-data-sources`.
