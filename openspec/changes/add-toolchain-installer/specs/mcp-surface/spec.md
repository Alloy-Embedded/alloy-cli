## ADDED Requirements

### Requirement: the MCP server SHALL expose `alloy.toolchain_status` and `alloy.toolchain_install_plan` read-only tools

`alloy mcp serve` SHALL register two new read-only tools:

`toolchain_status(family_id?: string)` returns the resolved
family manifest enriched with per-tool installed / missing /
version-mismatch state from the local toolchain store.  Each
returned tool entry SHALL carry the Wave 1
`list_family_toolchain` fields (tool, version, source,
capabilities, bundles, udev_required, install_docs) plus:

- `installed: bool` — whether the store currently has a
  matching extraction.
- `installed_version: string | null` — the version on disk if
  any.
- `installed_path: string | null` — the absolute path under
  `~/.local/share/alloy/tools/by-name/...` if installed.
- `state: "ok" | "missing" | "version-mismatch" | "vendor"`
  — categorical view for fast UI rendering.

`toolchain_install_plan(family_id: string)` returns the
**plan** only — the manager calls every adapter to resolve
URLs + sizes + sha256s WITHOUT downloading.  The response
shape is:

```
{
  "family_id": "stm32g0",
  "host": {"os": "macos", "arch": "arm64"},
  "plan": [
    {
      "tool": "arm-none-eabi-gcc",
      "version": "14.2.0",
      "source": "xpack",
      "url": "https://...",
      "sha256": "abc...",
      "size_bytes": 280123456
    }
  ],
  "skipped_vendor": [
    {"tool": "STM32CubeProgrammer", "install_doc_url": "https://..."}
  ],
  "total_size_bytes": 290000000
}
```

Both tools SHALL be classified read-only — they SHALL NOT
participate in the `preview_diff` / `apply_diff` cache and
SHALL NOT return a `diff_id`.

When the requested family id has no manifest, both tools SHALL
return `error_type="family-toolchain-not-found"` (the existing
Wave 1 envelope) with the same `known_families` list.

When the active host triple is unsupported (no adapter has a
pin matching the host), `toolchain_install_plan` SHALL surface
`error_type="family-toolchain-installer-unsupported-host"`
with the actual `host` triple in the envelope.

`toolchain_install_plan` SHALL NOT perform any network I/O.
`toolchain_status` SHALL NOT perform any network I/O.

#### Scenario: toolchain_status reports installed and missing

- **WHEN** an MCP client calls
  `alloy.toolchain_status(family_id="stm32g0")`
- **AND** the store has `arm-none-eabi-gcc 14.2.0` but lacks
  `probe-rs`
- **THEN** the response SHALL classify `arm-none-eabi-gcc`
  as `state="ok"` with a non-null `installed_path`
- **AND** SHALL classify `probe-rs` as `state="missing"`
- **AND** SHALL classify `STM32CubeProgrammer` as
  `state="vendor"`

#### Scenario: toolchain_install_plan returns plan without I/O

- **WHEN** an MCP client calls
  `alloy.toolchain_install_plan(family_id="stm32g0")`
- **THEN** the response SHALL include a `plan` array of
  every non-vendor required + recommended tool
- **AND** every plan entry SHALL carry `url`, `sha256`,
  and `size_bytes`
- **AND** the response SHALL include `skipped_vendor` for
  every vendor entry with its install doc URL
- **AND** no bytes SHALL be written to the toolchain store
  during the call

#### Scenario: unsupported host surfaces typed envelope

- **WHEN** an MCP client calls
  `toolchain_install_plan(family_id="esp32")`
- **AND** the active host triple is `linux-mips64`
  (not in any pin file)
- **THEN** the response SHALL be a typed error with
  `error_type="family-toolchain-installer-unsupported-host"`
- **AND** the envelope SHALL include the actual host triple
- **AND** SHALL include `supported_hosts` (the union of every
  declared host across the family's pins)

#### Scenario: tool list discovery includes the new tools

- **WHEN** an MCP client requests the tool list via
  `list_tools`
- **THEN** the returned set SHALL include both
  `toolchain_status` and `toolchain_install_plan`
- **AND** each tool's `description` SHALL be a non-empty
  docstring
- **AND** the parameter schema for `toolchain_status` SHALL
  declare `family_id` as optional
- **AND** the parameter schema for `toolchain_install_plan`
  SHALL declare `family_id` as required
