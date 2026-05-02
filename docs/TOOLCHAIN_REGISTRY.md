# Toolchain Registry — `data/families/*.yml`

`alloy-cli` decides which host tools your MCU project needs by
reading a per-family **toolchain manifest** under
[`data/families/`](../data/families/).  This document is the
contributor reference: what the manifest fields mean, how
inheritance works, and how to add a new family.

> Short version: a manifest is a YAML file describing the
> compiler, build orchestrator, flasher, debugger, and
> recovery tools required for one MCU family — keyed on the
> family id used in `alloy.toml [chip].family` or
> `boards/<id>/board.json#family`.

## Why it lives here, not in `alloy-devices-yml`

The canonical device IR (`alloy-devices-yml`) describes
*on-chip* facts — peripherals, pins, clock graph, DMA matrix.
Toolchain choice is a *host-side* decision that changes faster
than the IR (e.g. when xPack publishes a new arm-gcc).  Coupling
them would force a devices-yml release every time a toolchain
pin moved.  Manifests therefore ship with `alloy-cli` itself —
one alloy-cli release is the single source of truth for the
manifest contract Wave-2's installer will consume.

See `openspec/changes/add-toolchain-registry/design.md#d1` for
the full rationale.

## Schema reference

Every manifest is validated against
[`schema/family_toolchain_v1.json`](../schema/family_toolchain_v1.json)
(JSON Schema Draft 2020-12, `additionalProperties: false` at every
level).  The vocabulary:

### Top-level fields

| Field | Required | Type | Meaning |
|-------|----------|------|---------|
| `schema_version` | ✅ | `string`  | SemVer of the manifest schema (`^1\.[0-9]+\.[0-9]+$`).  Always `"1.0.0"` until we ship an additive change. |
| `family_id`      | ✅ | `string`  | Kebab-case identifier; **must match the YAML filename stem**. |
| `core`           | ✅ | `string`  | CPU core string — e.g. `cortex-m4f`, `cortex-m0plus`, `xtensa-lx6`. |
| `arch`           | ❌ | `string`  | Optional architecture identifier (e.g. `armv7em`, `armv6m`, `xtensa`). |
| `extends`        | ❌ | `string`  | Parent family id whose tool lists this manifest inherits. |
| `required[]`     | ❌ | `array`   | Tools the family **cannot** build / flash / debug without. |
| `recommended[]`  | ❌ | `array`   | Tools that materially improve UX (recovery, alt flashers, serial). |
| `optional[]`     | ❌ | `array`   | Power-user tools (alternative debuggers, SVD packs, …). |

`required` / `recommended` / `optional` arrays each contain
**tool requirement** objects — the inner schema described
below.

### Tool requirement fields

| Field | Required | Type | Meaning |
|-------|----------|------|---------|
| `tool`          | ✅ | `string` | Canonical binary / package name.  Kebab-case for CLIs (`arm-none-eabi-gcc`); PascalCase tolerated for vendor GUIs (`STM32CubeProgrammer`). |
| `version`       | ✅ | `string` | SemVer-style range (e.g. `">=14,<16"`) — Wave-2's installer evaluates it. |
| `source`        | ✅ | `string` | Where Wave-2 fetches the binary from.  Closed enum (see below). |
| `capabilities`  | ✅ | `string[]` | What this tool provides — closed enum (see below).  Must declare at least one. |
| `bundles`       | ❌ | `string[]` | Extra binaries shipped alongside the primary tool (e.g. `arm-none-eabi-gdb` ships with `arm-none-eabi-gcc`).  The registry flattens these so `tool_for_capability("debug")` resolves to the gcc entry. |
| `udev_required` | ❌ | `bool`   | Linux-only hint: this tool needs udev rules to access USB probes without `sudo`. |
| `install_docs`  | ❌ / ✅ | `object` | Per-OS install URLs.  **REQUIRED** when `source = "vendor"`; ignored otherwise. |

#### `source` — where the tool comes from

| Value | What it means |
|-------|---------------|
| `xpack` | xPack Binary Distribution — pre-built MIT-wrapped tarballs on GitHub Releases for Linux / macOS / Windows. |
| `github:<owner>/<repo>` | A GitHub release asset.  Owner + repo follow GitHub's username rules (alphanumeric + hyphens, case-preserving). |
| `probe-rs-installer` | Run probe-rs's official install script.  Probe-rs ships a single static Rust binary plus optional udev rules. |
| `espressif` | Espressif's own index server (`dl.espressif.com`).  Used for Xtensa + RISC-V ESP toolchains and SDK. |
| `vendor` | EULA-gated — Wave-2 will **never** auto-install.  Manifest **must** carry `install_docs` per OS instead.  `alloy doctor` renders these as `info` severity (not `error`) with the OS-appropriate URL. |

#### `capabilities` — what the tool does

Closed enum.  `alloy <verb>` maps to the first tool advertising
the matching capability:

| Value | Used by |
|-------|---------|
| `build` | `alloy build` (`cmake` / `ninja` / cross-gcc). |
| `flash` | `alloy flash`. |
| `debug` | `alloy debug` (gdb / probe-rs gdb-server). |
| `reset` | `alloy reset` (Wave-4) — soft target reset. |
| `recovery` | `alloy erase` / `alloy recover` (Wave-4) — chip-erase, RDP unlock, APPROTECT recovery. |
| `serial` | `alloy monitor` (Wave-4) — serial terminal (`tio`, `picocom`). |
| `register-debug` | Optional power-user view (CMSIS-SVD aware register decoding). |

Adding a value is a schema bump (1.0.x → 1.1.0 minor; clients
ignore unknown capabilities).

#### `install_docs` — per-OS vendor links

```yaml
install_docs:
  linux:   https://www.st.com/...
  macos:   https://www.st.com/...
  windows: https://www.st.com/...
```

At least one of `linux` / `macos` / `windows` must be present
(`minProperties: 1`).  Schema enforces that vendor-source tools
declare this object — we cannot redistribute EULA-gated binaries,
so the user has to download them manually.

## `extends` — single-parent inheritance

A child manifest inherits its parent's `required` / `recommended`
/ `optional` lists.  At load time the registry walks the chain
base → child and merges arrays **by tool name**:

* If a tool with the same `tool` field exists in both, the child's
  entry wins **and the entry stays at the parent's position**
  (so ordering remains predictable).
* New tools in the child are appended after every inherited tool.
* `core`, `arch`, and other top-level fields take the **child's**
  value (last write wins).
* `extends` itself is per-file — it does not propagate.  If you
  want a three-level chain (leaf → mid → root), put `extends` on
  the leaf (pointing at mid) and on mid (pointing at root).

Cycles raise `family-toolchain-cycle`; unknown parents raise
`family-toolchain-unknown-parent`.  Both are caught at YAML load
time so contributors see them immediately under `pytest`.

### Worked example: `arm-cortex-m` → `stm32f4`

[`data/families/arm-cortex-m.yml`](../data/families/arm-cortex-m.yml)
declares the four tools every Cortex-M project needs:

```yaml
schema_version: "1.0.0"
family_id: arm-cortex-m
core: cortex-m

required:
  - tool: arm-none-eabi-gcc
    version: ">=13,<16"
    source: xpack
    capabilities: [build, debug]
    bundles: [arm-none-eabi-gdb, arm-none-eabi-size, ...]
  - tool: cmake
    version: ">=3.25"
    source: xpack
    capabilities: [build]
  - tool: ninja
    version: ">=1.11"
    source: xpack
    capabilities: [build]
  - tool: probe-rs
    version: ">=0.27"
    source: probe-rs-installer
    capabilities: [flash, debug, reset]
    udev_required: true
```

[`data/families/stm32f4.yml`](../data/families/stm32f4.yml) extends
the base and adds STM32-specific recovery tooling:

```yaml
schema_version: "1.0.0"
family_id: stm32f4
core: cortex-m4f
arch: armv7em
extends: arm-cortex-m

recommended:
  - tool: STM32CubeProgrammer
    version: ">=2.16"
    source: vendor
    capabilities: [flash, recovery, register-debug]
    install_docs:
      linux:   https://www.st.com/en/development-tools/stm32cubeprog.html
      macos:   https://www.st.com/en/development-tools/stm32cubeprog.html
      windows: https://www.st.com/en/development-tools/stm32cubeprog.html
  - tool: dfu-util
    version: ">=0.11"
    source: github:Stefan-Schmidt/dfu-util
    capabilities: [flash]
  - tool: tio
    version: ">=2.7"
    source: github:tio/tio
    capabilities: [serial]
```

Calling `toolchain_registry.load_family("stm32f4")` returns a
manifest whose `required` is the four base tools (verbatim) and
whose `recommended` is the three stm32f4-specific tools.

## Add a new family — walkthrough

You want to ship a manifest for `samd51` (Microchip Cortex-M4F)?
The full procedure is a YAML PR with no code changes.

1. **Pick the family id**.  It must match the value
   `boards/<id>/board.json#family` and `alloy.toml [chip].family`
   already use.  If the family is brand-new to alloy-cli, pick a
   short, kebab-case identifier (`samd51`, not `SAMD51`).

2. **Copy the closest existing manifest as a template**.  For a
   Cortex-M family, `stm32f4.yml` is a good starting point — it
   already uses `extends: arm-cortex-m` and the vendor-tool
   pattern.  For a totally new architecture (RISC-V, MSP430, …)
   start from `esp32.yml`, which stands alone.

3. **Edit the top-level fields**:
   * `family_id` → your new id
   * `core` → the actual core (`cortex-m4f`, `riscv32imac`, …)
   * `arch` → optional architecture identifier
   * `extends` → drop or change as appropriate

4. **Curate the `recommended` / `optional` lists**:
   * Add vendor-specific recovery tools (e.g. `bossac` for SAMD,
     `nrfjprog` for nRF52) with the right `source`.
   * If the tool is EULA-gated, set `source: vendor` and fill
     `install_docs` for every supported OS.
   * Set `capabilities` honestly — `alloy reset` will reach for
     the first tool advertising `reset`.

5. **Validate locally**:

   ```sh
   .venv/bin/pytest tests/test_family_toolchain_schema.py -v
   .venv/bin/pytest tests/test_toolchain_registry.py -v
   ```

   The schema test will load + validate your new YAML; the
   registry test will exercise `load_family("<your-id>")` if you
   add it to the `SHIPPED` tuple.

6. **Smoke-test the doctor surface**:

   ```sh
   .venv/bin/alloy doctor --for <your-id>
   .venv/bin/alloy doctor --for <your-id> --json | jq .
   ```

   Confirm the table renders the right tool list and the
   `source` column is populated.

7. **Update the SHIPPED tuple** in
   [`tests/test_family_toolchain_schema.py`](../tests/test_family_toolchain_schema.py)
   and
   [`tests/test_toolchain_registry.py`](../tests/test_toolchain_registry.py)
   so the new family is part of CI's coverage matrix.

8. **Wire the manifest into the wheel** — add the YAML path to
   both `[tool.hatch.build.targets.wheel.shared-data]` and
   `[tool.hatch.build.targets.wheel.force-include]` in
   [`pyproject.toml`](../pyproject.toml).

9. **Open the PR**.  CI runs `openspec validate --strict`,
   `pytest`, `ruff`, and `pyright`; all must pass.

## Errors

Every failure path raises a typed error from the
`AlloyCliError` hierarchy.  See
[`docs/ERROR_COOKBOOK.md`](ERROR_COOKBOOK.md) for the
authoritative anchor list:

* [`family-toolchain-error`](ERROR_COOKBOOK.md#family-toolchain-error)
  — base type for the registry loader.
* [`family-toolchain-cycle`](ERROR_COOKBOOK.md#family-toolchain-cycle)
  — the `extends:` chain forms a cycle.
* [`family-toolchain-unknown-parent`](ERROR_COOKBOOK.md#family-toolchain-unknown-parent)
  — a manifest declares `extends: <id>` but no manifest exists
  for that id.
* [`family-toolchain-schema`](ERROR_COOKBOOK.md#family-toolchain-schema)
  — the YAML failed JSON Schema validation (the message names
  the offending JSON path).
* [`family-toolchain-not-found`](ERROR_COOKBOOK.md#family-toolchain-not-found)
  — the requested family id has no shipped manifest.

## Related references

* [`schema/family_toolchain_v1.json`](../schema/family_toolchain_v1.json)
  — the authoritative schema.
* [`src/alloy_cli/core/toolchain_registry.py`](../src/alloy_cli/core/toolchain_registry.py)
  — loader + `extends:` resolver + cache.
* [`src/alloy_cli/core/diagnose.py`](../src/alloy_cli/core/diagnose.py)
  — family-aware `alloy doctor` backend.
* [`openspec/changes/add-toolchain-registry/`](../openspec/changes/add-toolchain-registry/)
  — the OpenSpec proposal that introduced this capability.
