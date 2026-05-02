# Wire alloy-codegen Into the Build Pipeline

## Why

Today every `alloy.toml` is a complete description of the project,
but `alloy build` only invokes `cmake + ninja`.  The C++ headers the
firmware actually compiles against (`alloy/board/board.hpp`, the
typed `Uart<USART2>` template instantiations, peripheral register
maps) are expected to live under `.alloy/generated/include/` —
**produced by alloy-codegen**.  We never call alloy-codegen.

The result: every demo today either builds against pre-generated
headers checked into the project, or fails to link.  Power users
work around it by running `alloy-codegen generate` by hand before
`alloy build`.  That breaks the "one command rebuilds everything"
contract from `docs/VISION.md`.

This proposal closes the loop.

## What Changes

- **`core.codegen` module** — new wrapper around the alloy-codegen
  Python entry point.  Functions:
  - `regenerate_if_stale(config, layout) -> RegenResult` — checks
    `.alloy/generated/<device>/.stamp` against the IR file SHA +
    alloy-codegen pinned version + alloy-cli version; only invokes
    codegen when the stamp is missing or stale.
  - `force_regenerate(config, layout) -> RegenResult` — bypass
    the cache (called by `alloy build --regen`).
  - `discover_codegen_entry() -> CodegenEntry | None` — locates
    the installed `alloy_codegen` package, reports its version,
    and probes for the `generate(config: ProjectConfig, out_dir:
    Path) -> GenerateResult` callable.  Returns ``None`` when the
    package isn't installed; `core.build.run` keeps going (with a
    warning) so the existing flow continues to work in CI without
    the codegen dep installed.
- **`core.build.run` extension** — a new pre-cmake phase calls
  `core.codegen.regenerate_if_stale(...)` whenever a codegen entry
  is discoverable.  The build's `BuildResult` gains a
  `codegen_returncode` and a `codegen_skipped: bool` field so the
  CLI / TUI can surface the new step.
- **`alloy build --regen`** Click flag forces a full regeneration.
- **`alloy build --no-codegen`** Click flag skips the step (CI
  scenarios where headers are pre-shipped).
- **Lockfile coupling** — `.alloy/version.lock` already tracks the
  alloy-codegen version; the stamp file consumes it so a `pip
  install -U alloy-codegen` invalidates every project's cache on
  the next build.
- **MCP surface** — a new `alloy.regenerate` tool wraps
  `force_regenerate` so AI agents can request a fresh codegen pass
  before reasoning about generated headers.

## Impact

After this lands, **the user types `alloy build` and gets a fully
linked binary**.  No manual codegen step.  The TUI Build Log
screen automatically gains a "Codegen" phase indicator (the screen
already iterates on whatever phases the on_line callback emits).

The MCP server gains an end-to-end "AI rebuilds the project from a
single prompt" capability that today is blocked on the missing
codegen pass.

## What this DOES NOT do

- Does not vendor alloy-codegen — it's an optional dependency
  resolved at runtime via the lockfile.
- Does not change the canonical IR format; alloy-devices-yml and
  alloy-codegen retain their own contracts.
- Does not reorganise `.alloy/` cache layout; we add the stamp
  file under the existing `.alloy/generated/` tree.
- Does not implement multi-target codegen (one project, one
  generated tree).
