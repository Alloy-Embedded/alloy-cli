# Vision

> The first embedded developer tool that is **beautiful, scriptable,
> AI-native, and chip-agnostic — all four at once**.

## The problem we're solving

Embedded firmware development in 2026 is a tooling tax.  A typical
"blink the LED on a new dev board" looks like:

1. Open vendor IDE (CubeIDE, MCUXpresso, Code Composer Studio, IAR).
2. Pick chip from a tree menu.  Pin picker is graphical.
3. Generate boilerplate that uses **vendor HAL C code** — runtime
   strings, void-pointer state structures, no compile-time validation.
4. Edit the generated `main.c` to do anything useful.
5. Switch to a different IDE / tool to flash and debug.
6. Switch to a third tool to do CI.
7. Try to share the project with a colleague — they must install the
   exact IDE version because the project format is opaque.

Every step has a different tool with a different mental model.
Every chip family has a different vendor flavour of every step.
None of it is scriptable.  None of it is AI-friendly.  Configuration
is hidden in `.ioc`/`.project`/`.cproject` files no one can read.

## What `alloy-cli` does differently

**One tool.  Terminal-native.  Cross-vendor.  Type-safe at compile time.**

```bash
$ alloy new my-firmware --board nucleo_g071rb
$ cd my-firmware

$ alloy add uart                                # opens TUI pin picker
$ alloy add gpio --pin PA5 --label LED          # or use CLI args directly

$ alloy build                                   # arm-gcc auto-detected
$ alloy flash                                   # probe-rs auto-detected
$ alloy debug                                   # opens GDB session

$ alloy ui                                      # full TUI dashboard
```

Or, equivalent, AI-driven via any MCP-compatible client:

```
> blink the user LED at 1 Hz
LLM ↳ alloy.list_boards() ↳ alloy.query_device_ir(...)
    ↳ alloy.add_gpio(pin=PA5, label=LED) ↳ alloy.write_blink_loop(LED)
    ↳ alloy.build() ↳ alloy.flash()
```

Same operations, three entry points.  The CLI is for muscle memory and
CI.  The TUI is for discovery and configuration.  The MCP server is
for AI.

## Five non-negotiable principles

1. **Determinism is the floor.**  Every interactive operation has a
   scriptable CLI equivalent.  The TUI is a "view layer" — it never
   does work the CLI cannot.

2. **Validation lives in the IR, not the UI.**  Every "is this pin
   valid for USART1_TX?" answer comes from a queryable canonical
   IR.  The TUI only renders the IR's truth.  This makes the TUI
   correct by construction across 8 500+ chips with zero per-chip code.

3. **Compile-time safety is the wall.**  Even if the TUI / LLM / user
   makes a wrong choice, the C++23 HAL's `concept` / `static_assert`
   gates refuse to compile.  Two layers of defence: **IR validation
   at config time + concept validation at compile time.**

4. **AI-grounded, not AI-imagined.**  The MCP server exposes typed
   tools.  LLMs do not write raw register accesses.  Every patch
   passes through the same validators a human would hit, then through
   the C++ compiler.  Hallucination becomes detection.

5. **Beautiful is functional.**  Information density beats sparse
   marketing screens.  Color is data, not decoration.  Every screen
   is keyboard-first.  Output respects `NO_COLOR=1`, `--no-color`,
   plain xterm, screen readers.

## The competitive landscape

| Tool | Scriptable | TUI / GUI | Cross-vendor | Compile-time validated | AI-native |
|---|---|---|---|---|---|
| CubeMX (ST) | ❌ | GUI | ❌ ST only | ❌ | ❌ |
| MCUXpresso (NXP) | ❌ | GUI | ❌ NXP only | ❌ | ❌ |
| PlatformIO | ✓ | partial | ✓ | ❌ | ❌ |
| Modm / `lbuild` | ✓ | ❌ | ✓ ~3 000 chips | ❌ | ❌ |
| Zephyr `west` | ✓ | ❌ | Zephyr only | partial | ❌ |
| Cargo embedded | ✓ | ❌ | Rust only | ✓ | ❌ |
| **`alloy-cli`** | ✓ | **TUI** | ✓ | ✓ | ✓ MCP-native |

`alloy-cli` is the **only one that hits all five columns simultaneously**.
This is structurally possible because the Alloy ecosystem already has
the canonical IR (alloy-devices-yml), the typed C++ HAL (alloy/), and
the code generator (alloy-codegen) — three unique assets that took
~3 years to build and that competitors cannot bolt on.

See `docs/COMPARISON.md` for the per-feature breakdown.

## What we're explicitly **not** building

- A new IDE.  Use VS Code, Helix, vim, whatever.  We integrate, we
  don't replace.
- A new HAL.  alloy/ is the HAL.  alloy-cli is the dev surface around
  it.
- A new schema.  alloy-devices-yml's canonical YAML is the schema.
  We consume; we don't redefine.
- A new debug protocol.  probe-rs / OpenOCD / GDB are excellent.  We
  wrap, we don't compete.
- A web app.  Terminal-only.  Web is opt-in, future, optional.

## Why we'll win

Each piece reinforces the others:

- IR (alloy-devices-yml) → makes TUI correct by construction
- TUI → makes alloy approachable for newcomers
- HAL concepts (alloy/) → make config errors catch at compile time
- MCP server → lets every LLM agent use alloy as a power user
- Cross-vendor breadth → one tool to learn, all chips supported

Each addition is multiplicative, not additive.  Competitors would
need 3 years of Alloy ecosystem work *plus* the CLI to match — and at
that point they'd just be re-implementing alloy-cli.
