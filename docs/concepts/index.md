# Concepts

These pages explain the architectural ideas alloy-cli is built on.
Reading them is **optional** if you're just using the CLI — but it
helps when something doesn't behave the way you expect.

The five concepts:

1. **[Device IR](device-ir.md)** — every choice (pin, clock, DMA
   stream) is checked against a typed, schema-locked intermediate
   representation at config time, not at link time.
2. **[Toolchain orchestrator](toolchain-orchestrator.md)** — one
   walker (`install_family`) drives every install entry point so
   `alloy new`, `alloy doctor --fix`, `alloy setup`, the TUI
   Onboarding screen, and the MCP `toolchain_apply_install_plan`
   tool all behave identically.
3. **[Probe orchestrator](probe-orchestrator.md)** — same shape,
   different domain: one walker that owns probe selection +
   binary resolution + the typed-error vocabulary for `alloy
   reset` / `alloy erase` / `alloy monitor`, the TUI
   `MonitorScreen`, and six MCP probe tools.
4. **[Lockfile-aware execution](lockfile-aware-execution.md)** —
   the project's `.alloy/toolchain.lock` pins every binary by
   SHA256.  Build / flash / debug commands resolve absolute paths
   from the lockfile, never from `$PATH`.
5. **[Two-phase mutations](two-phase-mutations.md)** — every
   destructive op (apply diff, install toolchain, erase flash)
   has a *preview* tool the agent calls first; the *apply* tool
   refuses without explicit confirmation.

If you only have time for one, read **Toolchain orchestrator** —
it's the pattern the whole CLI surface is shaped around.
