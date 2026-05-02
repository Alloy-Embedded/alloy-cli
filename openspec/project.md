# Project Context

`alloy-cli` is the terminal-native developer surface for the **Alloy
embedded platform**.  It composes three sibling repos into one
beautiful, scriptable, AI-native tool:

- **`alloy-devices-yml`** — canonical IR per chip (~17 admitted today,
  8 505 pre-staged across 22 vendors)
- **`alloy-codegen`** — emits typed C++23 headers from the IR
- **`alloy`** — the C++ HAL + drivers + boards

`alloy-cli` does not duplicate any of those repos' data or logic.  It
**reads from them and orchestrates them** through three façades:

1. **CLI** (Click) — `alloy new`, `alloy add uart`, `alloy build`, …
2. **TUI** (Textual + Rich) — interactive pin picker, clock-tree
   visualiser, dashboard
3. **MCP server** — exposes the same operations as MCP tools so LLM
   agents (opencode, Claude Code, Cursor) can drive Alloy as a power
   user

## Foundational documents

Every proposal MUST be consistent with these:

- `docs/VISION.md` — what we're building and why
- `docs/COMPARISON.md` — vs CubeMX / PlatformIO / Modm / Zephyr west /
  cargo-embedded
- `docs/ARCHITECTURE.md` — three-façade structure, project format,
  data flow
- `docs/DATA_SOURCES.md` — exactly where every piece of information
  comes from
- `docs/TUI_DESIGN.md` — the screen catalogue + design principles +
  custom widgets
- `docs/ROADMAP.md` — five-phase plan, fifteen proposals

## Non-negotiable principles

(From `docs/VISION.md` — restated here for OpenSpec authors.)

1. **Determinism is the floor.**  Every interactive operation has a
   scriptable CLI equivalent.
2. **Validation lives in the IR**, not the UI.  Every "is this pin
   valid?" answer comes from `alloy-devices-yml` queries.
3. **Compile-time safety is the wall.**  C++23 `concept` /
   `static_assert` gates refuse to compile invalid wiring.
4. **AI-grounded, not AI-imagined.**  MCP tools dispatch into the
   same validators a human would hit.
5. **Beautiful is functional.**  Information density beats sparse
   marketing screens.  Color is data.

## Data flow

```
alloy-devices-yml/.../device.yml ──▶  alloy_cli.core.ir
                                            │
       alloy.toml (project)  ──────────────▶│
                                            ▼
                                   alloy_cli.core.{peripherals,
                                                   pins, dma,
                                                   clocks, project}
                                            │
       ┌────────────────────────────────────┼────────────────────────┐
       ▼                                    ▼                        ▼
  alloy_cli.cli (Click)             alloy_cli.tui (Textual)   alloy_cli.mcp
  → flags, exit codes               → screens, widgets         → MCP tools
```

## Vocabulary

- **IR**: the canonical device intermediate representation, one YAML
  per chip in `alloy-devices-yml`.
- **Project**: a user's firmware project, characterised by an
  `alloy.toml` and a `.alloy/` cache directory.
- **Façade**: one of the three user surfaces (CLI / TUI / MCP).  All
  three call `core/`.
- **Operation**: a state-changing function in `core/` (e.g.,
  `add_uart`, `set_clock_profile`).  Operations always return a
  `UnifiedDiff`; they never mutate the project on their own.
- **Apply**: commit a previewed `UnifiedDiff` to the filesystem.

## Code style

- Python 3.11+.
- `ruff check` clean.
- `pyright --strict` for `src/alloy_cli/core/`.
- Module docstrings explain purpose; function docstrings explain
  contract.
- No emojis in code; UI glyphs are deliberate (see
  `docs/TUI_DESIGN.md`).

## Testing

- Unit tests for `core/` — fast, no I/O.
- Snapshot tests for TUI screens — `pytest-textual-snapshot`.
- Smoke tests for end-to-end flows — `alloy new` → `alloy build`.

## OpenSpec workflow

- Every change is one OpenSpec proposal.
- Proposals describe **what** and **why**, with scenarios.
- `openspec validate <id> --strict` must pass before merge.
- One reviewer + one OpenSpec validator approval to land.
