## ADDED Requirements

### Requirement: the MCP server SHALL expose an `alloy.list_family_toolchain` tool

`alloy mcp serve` SHALL register a read-only tool named
`list_family_toolchain` that returns the resolved toolchain
manifest for a given MCU family.  The tool's parameter schema
SHALL declare a single required `family_id: string` argument.
The tool SHALL invoke
`core.toolchain_registry.load_family(family_id)` and project the
returned `FamilyManifest` to a JSON-friendly dictionary with the
following shape:

```
{
  "family_id":     "stm32g0",
  "core":          "cortex-m0plus",
  "arch":          "armv6m",
  "schema_version": "1.0.0",
  "required":      [ <ToolRequirement>, ... ],
  "recommended":   [ <ToolRequirement>, ... ],
  "optional":      [ <ToolRequirement>, ... ]
}
```

Each `ToolRequirement` SHALL be a flat object containing
`tool`, `version`, `source`, `capabilities` (list),
`bundles` (list), `udev_required` (bool), and `install_docs`
(object) — the same fields the manifest declares.

The tool SHALL be classified as read-only: it SHALL NOT
participate in the `preview_diff` / `apply_diff` cache and SHALL
NOT return a `diff_id`.

When the requested family id has no manifest, the tool SHALL
return a structured error envelope with
`error_type="family-toolchain-not-found"` and a `known_families`
list of every family id alloy-cli ships a manifest for.

#### Scenario: list_family_toolchain returns a known manifest

- **WHEN** an MCP client calls
  `alloy.list_family_toolchain(family_id="stm32g0")`
- **THEN** the response SHALL include `family_id="stm32g0"`,
  `core`, `arch`, and a non-empty `required` array
- **AND** the `required` array SHALL contain entries for
  `arm-none-eabi-gcc`, `cmake`, `ninja`, and `probe-rs`
- **AND** every entry SHALL declare a `source` string

#### Scenario: list_family_toolchain returns vendor-source recommended tools

- **WHEN** an MCP client calls
  `alloy.list_family_toolchain(family_id="stm32f4")`
- **THEN** the `recommended` array SHALL contain an entry for
  `STM32CubeProgrammer` with `source="vendor"`
- **AND** that entry SHALL declare an `install_docs` object with
  `linux`, `macos`, and `windows` URL keys

#### Scenario: unknown family returns a typed error envelope

- **WHEN** an MCP client calls
  `alloy.list_family_toolchain(family_id="nonexistent")`
- **THEN** the response SHALL be an MCP error with
  `error_type="family-toolchain-not-found"`
- **AND** the response SHALL include a `known_families` list of
  every shipped family id

#### Scenario: tool list includes `list_family_toolchain` on discovery

- **WHEN** an MCP client requests the tool list via
  `list_tools`
- **THEN** the returned set SHALL include `list_family_toolchain`
- **AND** the tool SHALL declare a non-empty `description`
  matching its docstring
- **AND** the parameter schema SHALL declare `family_id: "string"`
