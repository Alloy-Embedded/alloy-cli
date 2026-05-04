# Toolchain management

alloy-cli ships its own per-MCU-family toolchain manager.  No
package-manager-of-the-month required: every project gets a
content-addressed, SHA-pinned, lockfile-tracked set of binaries
that build / flash / debug all resolve from.

Three reference docs cover the full surface:

- **[Onboarding](../TOOLCHAIN_ONBOARDING.md)** — Wave 3.  Every
  entry point that installs the toolchain (alloy new prompt,
  alloy doctor --fix, alloy setup, TUI Onboarding screen, MCP
  apply tool) and the shared orchestrator they all dispatch
  through.
- **[Installer](../TOOLCHAIN_INSTALLER.md)** — Wave 2.  The
  per-source pin file format (xpack, GitHub, probe-rs-installer,
  Espressif), the content-addressed store layout, the
  `.alloy/toolchain.lock` schema, the trust model.
- **[Registry](../TOOLCHAIN_REGISTRY.md)** — Wave 1.  The
  per-MCU-family manifest format, the `extends:` chain
  (`arm-cortex-m` → `stm32g0`), and the `alloy doctor --for
  <family>` command.

## At a glance

```sh
alloy new firmware --board nucleo_g071rb     # post-scaffold prompt
alloy setup --board nucleo_g071rb --auto     # wizard for fresh machines
alloy doctor --fix                           # repair an existing project
alloy doctor --fix --with-recommended        # also install recommended tier
alloy toolchain list                         # what's pinned vs available
alloy toolchain install --for stm32g0        # explicit re-install
```

For the conceptual underpinnings:

- [Toolchain orchestrator](../concepts/toolchain-orchestrator.md)
- [Lockfile-aware execution](../concepts/lockfile-aware-execution.md)
- [Two-phase mutations](../concepts/two-phase-mutations.md)
