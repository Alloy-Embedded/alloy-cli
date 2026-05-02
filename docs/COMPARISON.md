# Comparison

Honest, feature-by-feature comparison of `alloy-cli` against the
incumbents.  We're going to lose on some axes (community size,
maturity); we win structurally on others (IR-grounded validation,
AI-native, terminal beauty).

## Surface area

| Capability | CubeMX | MCUXpresso | PlatformIO | Modm/lbuild | Zephyr west | Cargo embedded | **alloy-cli** |
|---|---|---|---|---|---|---|---|
| Board / chip catalog | ST only | NXP only | ~10 000 | ~3 000 | Zephyr-only | Rust crates | **8 500+ via alloy-devices-yml** |
| Project scaffolder | partial (.ioc) | partial | ✓ `pio init` | ✓ `lbuild build` | ✓ `west init` | ✓ `cargo new` | ✓ `alloy new` |
| Pin picker | **GUI ★★★★★** | GUI ★★★ | none | textual config | none | none | **TUI ★★★★★** |
| Clock-tree visualiser | **GUI ★★★★★** | GUI ★★★★ | none | none | none | none | **TUI ★★★★** |
| DMA matrix | GUI ★★★ | GUI ★★ | none | none | none | none | **TUI ★★★** |
| Memory-map view | partial | partial | none | none | partial | partial | **TUI ★★★** |
| `build` | external IDE | IDE | `pio run` | external | `west build` | `cargo build` | `alloy build` |
| `flash` | external | IDE | `pio run -t upload` | external | `west flash` | `cargo embed` | `alloy flash` |
| `debug` | external IDE | IDE | partial | external | `west debug` | `cargo embed` | `alloy debug` |
| Toolchain detection | bundled | bundled | bundled | manual | manual | rustup | **auto + suggest** |
| CI scaffolding | none | none | partial | none | none | partial | **`alloy export ci`** |
| Probe agnostic | ❌ | ❌ | ✓ | ✓ | ✓ | ✓ | **✓ (probe-rs first)** |
| Compile-time peripheral validation | ❌ | ❌ | ❌ | ❌ | partial | partial | **✓ C++23 concepts** |
| AI / MCP integration | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **✓ MCP server** |
| Project format human-readable | ❌ `.ioc` opaque | ❌ binary | ✓ `.ini` | ✓ Python | ✓ DT | ✓ TOML | **✓ TOML + `.alloy/`** |
| Scriptable from shell | ❌ | ❌ | ✓ | ✓ | ✓ | ✓ | **✓** |

## The five battles

### 1. Pin picker

**CubeMX is the gold standard** — point at a pin, see every alternate
function, click to assign, watch conflicts highlight in red.  No
competitor has matched it in 15 years.

We match it in the terminal.  Same information density, every
constraint validated against the canonical IR.  Crucially: **for any
chip in alloy-devices-yml**, not just one vendor.

### 2. Configuration safety

Everyone except cargo-embedded loses here.  Cube generates C HAL with
runtime checks.  PIO has no checks.  Modm validates at config time
but not at compile time.  Zephyr has Devicetree compile-time validation
but only inside Zephyr's idiom.

`alloy-cli` ships **two layers**:

* **Config-time** — TUI / CLI refuses invalid pins because the IR
  says they can't.
* **Compile-time** — C++23 `ValidPinAssignment<P, S>`, `ValidDmaBinding`,
  `ValidI2cSpeed` concepts refuse to compile invalid wiring even if
  the user (or LLM) somehow bypasses the config layer.

The combination is unique in embedded.

### 3. AI integration

Nothing in the comparison row supports MCP today.  GitHub Copilot for
firmware is hit-or-miss because the LLM has no way to know what
peripherals exist on the chip — it improvises register addresses from
training data.

`alloy-cli` exposes the IR as MCP tools.  LLMs become **grounded**:
they ask the IR for valid pins / DMA channels, then call our
`add_*` operations, which themselves validate against the IR, which
themselves emit C++ that fails compile if anything slipped.

This isn't a feature — it's a different operating model.

### 4. Beauty

Modm / Zephyr / cargo-embedded are all **functional but plain**.  CLI
output is text-on-text, no information hierarchy, no visual
peripheral browser.

CubeMX wins on visual hierarchy in a GUI.  Nothing wins on visual
hierarchy in a terminal — that is `alloy-cli`'s opportunity.

Textual + Rich let us produce CubeMX-quality information density in
the terminal.  See `docs/TUI_DESIGN.md` for the screens.

### 5. Vendor lock-in

CubeMX is the worst.  MCUXpresso second.  PlatformIO is broad but
opinionated.  Modm covers ARM Cortex-M only.  Zephyr is Zephyr.
Cargo-embedded is Rust.

`alloy-cli` is bound to the alloy-devices-yml catalogue — which is
already at 8 500+ chips covering ST, NXP, Microchip, Nordic,
Espressif, Raspberry Pi, Cypress / Infineon, Nuvoton, TI, Renesas,
…

Adding a new chip is a YAML commit, not a CLI fork.

## What we lose at

- **Community / mindshare** — CubeMX is 15 years of installed base
  in vendor labs; PlatformIO has 10+.  We earn this slowly.
- **Vendor partnerships** — ST will not blast emails about us
  initially.  Adoption is bottom-up, not enterprise sales.
- **Toolchain bundling** — CubeIDE installs arm-gcc for you.  We
  detect and suggest install; we don't bundle the world.
- **GUI convenience for non-CLI users** — some embedded engineers
  fear the terminal.  We accept that segment as out-of-scope.
- **Maturity** — every other tool has years of bug-fixing.  We start
  at zero.  Mitigated by: small surface, good test coverage, IR
  validation catching most "would-be" bugs.

## Honest take

`alloy-cli` is competitive if and only if:

1. Phase 1-2 (deterministic CLI) lands solid in 8-10 weeks.
2. Phase 3 (TUI pin picker) ships at CubeMX quality, not "plain table".
3. Phase 4 (MCP) lands when MCP is mature enough that Claude Code /
   opencode / Cursor users actively want it (today: yes).

If we miss any of those bars we ship a worse Modm.  If we hit them
we ship something none of the incumbents can copy without rebuilding
3 years of Alloy ecosystem work.

That's the trade we're making.
