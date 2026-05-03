# alloy-cli — cheatsheet

Auto-generated from the live Click command tree.  Run `python scripts/generate_cheatsheet.py` after adding or renaming a subcommand.

## `alloy add adc`

Add an ADC peripheral with one or more channels.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--channel` — Repeatable; e.g. --channel 0:PA0 --channel 1:PA1.
  - `--resolution` — 
  - `--sample-time-cycles` — 
  - `--dma` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add can`

Add a CAN bus peripheral.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--tx` — 
  - `--rx` — 
  - `--bitrate` — 
  - `--sample-point` — 
  - `--fd, --no-fd` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add dac`

Add a DAC channel.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--channel` — **required.** 
  - `--pin` — **required.** 
  - `--output-buffer, --no-output-buffer` — 
  - `--trigger` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add eth`

Add an Ethernet peripheral (MII / RMII).

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--interface` — **required.** 
  - `--phy-address` — 
  - `--mdc` — 
  - `--mdio` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add gpio`

Add a GPIO peripheral.

Options:
  - `--name` — **required.** 
  - `--pin` — **required.** 
  - `--mode` — 
  - `--pull` — 
  - `--speed` — 
  - `--label` — 
  - `--initial` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add i2c`

Add an I2C peripheral.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--sda` — 
  - `--scl` — 
  - `--speed` — 
  - `--addressing` — 
  - `--dma` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add pwm`

Add a PWM channel.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--channel` — **required.** 
  - `--pin` — **required.** 
  - `--frequency-hz` — 
  - `--duty-cycle` — 
  - `--polarity` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add spi`

Add an SPI peripheral.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--sck` — 
  - `--miso` — 
  - `--mosi` — 
  - `--cs` — 
  - `--cs-software` — 
  - `--mode` — 
  - `--frame` — 
  - `--prescaler` — 
  - `--dma` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add timer`

Add a timer peripheral.

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--period-ns` — **required.** 
  - `--divider` — 
  - `--mode` — 
  - `--interrupt` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add uart`

Add a UART/USART peripheral.

Options:
  - `--name` — **required.** Peripheral identifier in alloy.toml.
  - `--peripheral` — IP instance, e.g. USART1 (default: lowest free).
  - `--tx` — TX pin (default: first IR-valid candidate).
  - `--rx` — RX pin (default: first IR-valid candidate).
  - `--baud` — 
  - `--data-bits` — 
  - `--stop-bits` — 
  - `--parity` — 
  - `--dma` — 
  - `--tx-dma` — 
  - `--rx-dma` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy add usb`

Add a USB peripheral (device / host / otg).

Options:
  - `--name` — **required.** 
  - `--peripheral` — 
  - `--mode` — **required.** 
  - `--vbus-sense, --no-vbus-sense` — 
  - `--speed` — 
  - `--project-dir` — 
  - `--diff-only` — Print the diff and exit.  Default when --apply is omitted.
  - `--apply` — Write the diff (default: --diff-only).

## `alloy boards`

List + search the curated board catalogue.

Options:
  - `--search` — Free-text query.
  - `--vendor` — Filter by vendor (e.g. st, rp).
  - `--isa` — Filter by core / ISA (e.g. cortex-m4).
  - `--has` — Require a feature; repeatable (e.g. --has usb --has ethernet).
  - `--tier` — Filter by support tier.
  - `--json` — Emit JSON for scripting.
  - `--pinout` — Open the read-only schematic pinout view in a Textual session.

## `alloy build`

Build the firmware for the current project.

Options:
  - `--profile` — Build profile (maps to CMAKE_BUILD_TYPE).
  - `--clean` — Wipe .alloy/build before configuring.
  - `--regen` — Force a fresh alloy-codegen pass (ignores the .stamp cache).
  - `--no-codegen` — Skip the alloy-codegen step entirely (CI scenarios with pre-shipped headers).
  - `--project-dir` — Project root containing alloy.toml.

## `alloy chat`

Launch opencode wired up to the alloy MCP server.

Options:
  - `--client` — LLM client to launch / emit config for.
  - `--print-config` — Emit the MCP config snippet for the chosen client and exit (no launch).
  - `--print-prompt` — Emit the bundled system prompt to stdout and exit.
  - `--project-dir` — Project directory passed to the MCP server's --cwd flag.

## `alloy debug`

Launch probe-rs gdb-server + attach GDB.

Options:
  - `--probe` — Probe selector forwarded to probe-rs.
  - `--target` — Override the chip name (default: from alloy.toml).
  - `--gdb-ui` — Override the GDB binary (default: ALLOY_GDB env var, then arm-none-eabi-gdb).
  - `--gdb-port` — TCP port for the gdb-server.
  - `--elf` — Path to the firmware ELF.
  - `--project-dir` — Project root containing alloy.toml.
  - `--dry-run` — Print the gdb-server + GDB invocations without running them.
  - `--tui, --no-tui` — Launch the Textual DebugScreen instead of the wrapper.  Defaults to --tui on a TTY, --no-tui otherwise.

## `alloy devices`

List + search the canonical device IR.

Options:
  - `--search` — Free-text query.
  - `--vendor` — Filter by vendor (e.g. st, nordic).
  - `--family` — Filter by family (e.g. stm32g0).
  - `--has` — Require a feature; repeatable (e.g. --has usb --has ble).
  - `--admitted, --all` — Restrict to admitted devices (default) or include bulk-admitted.
  - `--json` — Emit JSON for scripting.

## `alloy doctor`

Diagnose the host environment for alloy-cli.

Options:
  - `--json` — Emit JSON.
  - `--fix` — Run every available auto-fix; exits 0 only when no error rows remain.
  - `--with-recommended` — Extend the toolchain auto-installer to the family's recommended tier (default: required tier only).
  - `--for` — Inspect the toolchain for a specific MCU family (e.g. stm32g0, rp2040, esp32) instead of inferring it from the project's alloy.toml.  Useful before scaffolding.
  - `--project-dir` — Project root containing alloy.toml.

## `alloy export`

Emit auxiliary configuration files.

Options:
  - `--target` — Sub-target (e.g. github / gitlab / jenkins for `alloy export ci`).
  - `--project-dir` — 
  - `--dry-run` — Print the generated content to stdout instead of writing files.

## `alloy flash`

Flash the firmware via probe-rs.

Options:
  - `--probe` — Probe selector: auto, jlink, stlink, picoprobe, cmsis-dap, …
  - `--target` — Override the chip name passed to probe-rs (default: from alloy.toml).
  - `--elf` — Path to the firmware ELF (default: most recent build under .alloy/build/).
  - `--project-dir` — Project root containing alloy.toml.

## `alloy mcp serve`

Run the alloy MCP server (stdio default).

Options:
  - `--transport` — Transport for the MCP server.  HTTP / SSE land with the official SDK.
  - `--cwd` — Project directory exposed to MCP tools.

## `alloy new`

Scaffold a new alloy-cli firmware project.

Options:
  - `--board` — Board id (run `alloy boards` to list).  Mutually exclusive with --device.
  - `--device` — Chip-only project: e.g. st/stm32g0/stm32g071rb.  Mutually exclusive with --board.
  - `--license` — License header for the generated LICENSE file.
  - `--author` — Copyright holder for the LICENSE template.
  - `--git, --no-git` — Initialise a git repo with a single 'alloy new' commit.
  - `--force` — Allow scaffolding into a non-empty directory.
  - `--path` — Destination directory.  Defaults to ./<NAME>.
  - `--from-example` — Scaffold from a docs/EXAMPLES entry (e.g. 01-blinky, 02-uart-echo).  Mutually exclusive with --board / --device.
  - `--install-toolchain, --no-install-toolchain` — Install the family's toolchain after scaffolding.  Default in a TTY: Y (prompts unless --auto).  Default elsewhere: N.
  - `--auto` — Skip every interactive confirmation.  Combine with --install-toolchain to perform the install non-interactively.

## `alloy reset`

Reset the connected probe target.  Default is a soft CPU reset; pass --hard to pulse nRST.  Lockfile-aware: the probe-rs binary comes from .alloy/toolchain.lock when present.

Options:
  - `--soft, --hard` — Reset method: --soft (CPU reset, default) or --hard (nRST line).
  - `--halt-after-reset` — Leave the core halted after reset so a debugger can attach.
  - `--probe` — Explicit probe selector (matches alloy flash --probe).  Each field is optional — '0483' matches every ST-Link, '0483:374b' matches every ST-Link/V2-1, the full triple pinpoints one probe.
  - `--project-dir` — Project root containing .alloy/toolchain.lock.

## `alloy setup`

Guided onboarding for a fresh machine: detect or scaffold a project, then install its toolchain through the shared orchestrator (the same path `alloy new` and `alloy doctor --fix` use).

Options:
  - `--board` — Pre-pick a board (skips the picker step).
  - `--family` — Pre-pick a family; mutually exclusive with --board.
  - `--auto` — Suppress every interactive prompt with the default answer (Y on each install confirmation).
  - `--no-tui` — Force the line-based wizard even when STDIN is a TTY.  (Wave 3: line-based is the only path; this flag is a forward-compatible no-op.)
  - `--project-dir` — Project root.  Defaults to the current directory.

## `alloy toolchain install`

Download + verify + extract every non-vendor tool the family declares.

Options:
  - `--for` — MCU family id (default: resolved from the project's alloy.toml).
  - `--shared` — Install only into the global store; do NOT update the project lockfile.
  - `--dry-run` — Print the plan + estimated total size without writing anything.
  - `--include-optional` — Also install the family's optional tools.
  - `--force` — Re-download even when the SHA matches an already-installed entry.
  - `--project-dir` — Project root (used for family resolution + lockfile updates).

## `alloy toolchain list`

Show the per-family tool list with install state.

Options:
  - `--for` — 
  - `--installed` — Show only tools that are installed.
  - `--missing` — Show only tools that are not installed.
  - `--include-optional` — Include the family's optional tools in the listing.
  - `--json` — Emit JSON.
  - `--project-dir` — 

## `alloy toolchain prune`

Garbage-collect store entries no project lockfile pins.

Options:
  - `--dry-run` — List candidates without deleting.
  - `--projects-root` — One or more directories to scan recursively for `.alloy/toolchain.lock` files.  Repeat to add more.  Default: the current --project-dir only.
  - `--project-dir` — 

## `alloy toolchain shell`

Spawn a subshell with PATH augmented for cached toolchain binaries.

Options:
  - `--for` — 
  - `--print-path` — Print the augmented PATH instead of spawning a subshell.
  - `--project-dir` — 

## `alloy toolchain use`

Pin a specific tool version in .alloy/toolchain.lock.

Options:
  - `--project-dir` — 

## `alloy ui`

Launch the alloy Textual UI.

Options:
  - `--theme` — Theme name (default: $ALLOY_TUI_THEME or default_dark).
  - `--project-dir` — Project root containing alloy.toml.

## `alloy update`

Atomically upgrade pinned alloy components.

Options:
  - `--dry-run` — Print the upgrades that would happen without applying.
  - `--frozen` — Refuse any change.  Useful for CI.
  - `--project-dir` —
