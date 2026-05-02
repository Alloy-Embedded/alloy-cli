# Error Cookbook

Every error alloy-cli emits carries a stable
`AlloyCliError.error_type` string.  This cookbook documents
each one — what triggers it, what the message looks like, how
to fix it, and which MCP tool agents should call.

A CI script (`scripts/check_error_cookbook.py`) asserts every
declared `error_type` has an anchor here.  If you land a new
error type, you'll be reminded to update this file.

## DeviceNotFoundError

**Trigger:** the IR loader can't find a device YAML for the
requested `(vendor, family, device)` triple.

**Example message:** `device st/stm32g0/stm32xyz not found
under data/devices/vendors/`.

**Fix:**
- Confirm the device exists via `alloy devices --vendor st
  --family stm32g0 stm32xyz`.
- If the YAML is in the bulk-admitted set, pass
  `--include-bulk` to the search.
- If the submodule is uninitialised, `alloy doctor --fix` runs
  `git submodule update --init`.

**MCP tool:** `alloy.list_devices(query="stm32xyz")`.

## BoardNotFoundError

**Trigger:** the board catalog has no entry for the requested
ID.

**Example message:** `board nucleo_xyz not found in
the curated catalogue`.

**Fix:**
- Run `alloy boards` (no args) to see every curated board.
- Run `alloy boards <id> --pinout` to verify the entry exists
  before scaffolding.

**MCP tool:** `alloy.list_boards(query="nucleo")`.

## ProjectConfigError

**Trigger:** `alloy.toml` fails JSON-Schema validation or
contains a structural inconsistency (e.g. `[clocks].profile`
references a non-existent profile).

**Example message:** `alloy.toml [clocks].profile = "fast" but
[clocks].profiles has no entry by that name.`.

**Fix:** the message names the offending field; edit the file
or use `alloy add <kind>` instead of hand-editing.

**MCP tool:** `alloy.read_alloy_toml()` to confirm the
parsed shape.

## ProjectConfigVersionError

**Trigger:** `alloy.toml` declares a `schema_version` whose
major doesn't match what alloy-cli understands (currently
major 1).

**Example message:** `alloy.toml declares schema_version
"2.0.0" (major=2); this alloy-cli understands major=1.  Run
"alloy update" to upgrade alloy-cli.`

**Fix:** run `alloy update` (or `pip install -U alloy-cli`).
If you need to stay on the older alloy-cli, downgrade the
`schema_version` field.

**MCP tool:** none — this is a tool-version mismatch.

## PinInvalidError

**Trigger:** a peripheral payload references a pin that isn't
in the IR's connection_candidates for that peripheral +
signal.

**Example message:** `Pin PA12 is not a legal USART1.TX
mapping for this device.  Suggestions: PA9, PB6.`

**Fix:** pick one of the suggested pins, or omit the field
entirely so `core.suggestions.suggest_pin` picks a default.

**MCP tool:** `alloy.suggest_pins(vendor=..., family=...,
device=..., peripheral="USART1", signal="TX")`.

## DmaConflictError

**Trigger:** an explicit `tx_dma` / `rx_dma` channel collides
with another peripheral's claim.

**Example message:** `DMA1#1 already claimed by spi.flash_bus
(rx_dma).`

**Fix:** drop the explicit channel and let `--dma`
auto-allocate via `suggest_dma_pair`, or pick a different
channel from `alloy.query_device_ir(...).dma_routes`.

**MCP tool:** `alloy.query_device_ir(...)` then inspect
`dma_routes`.

## ToolchainMissingError

**Trigger:** a required CLI tool (`cmake`, `ninja`,
`arm-none-eabi-gcc`, `probe-rs`, `gdb`) isn't on `$PATH`.

**Example message:** `arm-none-eabi-gcc is not installed:
brew install --cask gcc-arm-embedded`.

**Fix:** install the missing tool — the message includes the
canonical install command for the active OS.  `alloy doctor`
flags every missing tool at once.

**MCP tool:** `alloy.doctor()` (alias to listing every check).

## DataRepoMissingError

**Trigger:** the alloy-devices-yml submodule isn't checked
out, so the IR loader has no data to work with.

**Example message:** `alloy-devices-yml submodule is not
initialised — run "git submodule update --init" from the
alloy-cli root.`

**Fix:** `alloy doctor --fix` runs the submodule init for
you, or do it manually.

**MCP tool:** none — this is a checkout-state problem.

## StaleDiffError

**Trigger:** an MCP `apply_diff` call references a `diff_id`
older than the 5-minute TTL.

**Example message:** `diff_id 'abc123…' has expired (300s
window).`

**Fix:** re-call the original `preview_diff` to get a fresh
ID.  Agents should treat preview → apply as a tight pair.

**MCP tool:** re-run the matching `add_*` or
`save_clock_profile` to get a new `diff_id`.

## peripheral-add-error

**Trigger:** any internal failure inside a typed
`add_*` operation that doesn't fit the more specific
categories (e.g. malformed payload that escaped JSON-Schema).

**Example message:** `add_uart: missing required field
'tx_dma' when 'dma=True' and no auto-allocation routes
exist.`

**Fix:** read the message — it always names the missing /
malformed field plus the right next step.

**MCP tool:** `alloy.suggest_pins(...)` /
`alloy.query_device_ir(...)`.

## probe-not-found

**Trigger:** `alloy flash` runs but no probe matches the
requested kind / serial.

**Example message:** `No probe matched kind='stlink'.
Connect one or pass --probe auto.`

**Fix:** plug the probe in (or check the USB cable!).
`probe-rs list` shows what the host actually sees.

**MCP tool:** `alloy.flash(elf=..., probe_kind="auto")`.

## multiple-probes

**Trigger:** more than one matching probe is connected and
the user didn't disambiguate.

**Example message:** `Multiple stlink probes detected; pass
--probe stlink:<serial>.`

**Fix:** pass the serial number, e.g. `alloy flash --probe
stlink:0682FF54...`.

**MCP tool:** `alloy.flash(elf=..., probe_kind="stlink:<sn>")`.

## gdb-not-found

**Trigger:** `alloy debug` can't locate the user's GDB front-end
(env var `ALLOY_GDB` or fallback `arm-none-eabi-gdb`).

**Example message:** `arm-none-eabi-gdb is not on $PATH.  Set
ALLOY_GDB or install the toolchain.`

**Fix:** install the cross-toolchain (or set `ALLOY_GDB` to a
path).  `alloy debug --no-tui` keeps the wrapper-only flow if
you don't need the TUI front-end.

**MCP tool:** none — this is a host-tool problem.

## codegen-error

**Trigger:** alloy-codegen's `generate(config, out_dir)`
callable raised; the most common cause is a vendor adapter
choking on a malformed peripheral payload.

**Example message:** `codegen-error: KeyError('clocks.profile')`

**Fix:** the message wraps the original exception — run
`alloy doctor` to confirm alloy-codegen is installed at the
right version, then check
`.alloy/cache/alloy-cli.log` for the full traceback.

**MCP tool:** `alloy.regenerate()` to re-run the codegen
pass once the input is corrected.

## scaffold-error

**Trigger:** `alloy new` (CLI / TUI / `--from-example`) failed
to create the project tree (permission denied, target dir
already exists, missing template, etc.).

**Example message:** `Cannot scaffold into 'blinky/': target
directory exists and is non-empty.`

**Fix:** pick a different name, pass `--force`, or remove the
existing dir.

**MCP tool:** none — scaffolding lives outside the MCP
contract.

## unknown-clock-profile

**Trigger:** `alloy.activate_clock_profile(name)` references
a profile not declared in `[clocks.profiles]`.

**Example message:** `Clock profile 'fast' is not defined in
[clocks].profiles (known: dev_low_power, default_pll_64mhz)`.

**Fix:** call `alloy.save_clock_profile` first to create the
profile, or `alloy.read_alloy_toml()` to see what's actually
declared.

**MCP tool:** `alloy.save_clock_profile(name=..., rates=...)`.

## duplicate-clock-profile

**Trigger:** the TUI's "Save profile" modal got a name that
already exists in `[clocks.profiles]` and the caller chose
not to overwrite.

**Example message:** `Profile 'dev_low_power' already
exists.`

**Fix:** pick a different name or confirm overwrite via the
follow-up prompt.

**MCP tool:** none — TUI-only path.

## invalid-clock-profile-name

**Trigger:** profile names must match `[a-zA-Z][a-zA-Z0-9_]*`.

**Example message:** `Profile name '9bad' must start with a
letter.`

**Fix:** rename to start with a letter and contain only
alphanumerics + underscores.

**MCP tool:** retry `alloy.save_clock_profile` with a valid
name.

## unknown-pin

**Trigger:** the requested pin isn't in the device's IR pin
list at all (different from PinInvalidError, which means the
pin exists but isn't legal for this peripheral).

**Example message:** `Pin PX99 is not on the
stm32g071rb LQFP64 package.`

**Fix:** check the pinout via `alloy boards <id> --pinout`,
or `alloy.suggest_pins(...)` from MCP.

**MCP tool:** `alloy.suggest_pins(...)`.

## diff-not-found

**Trigger:** MCP `apply_diff(diff_id=...)` references an ID
the cache doesn't know.

**Example message:** `Unknown diff_id 'xyz789…'.`

**Fix:** call the matching `preview_diff` / `add_*` first to
get a fresh ID.

**MCP tool:** retry the original preview call.

## tool-not-found

**Trigger:** MCP `call(tool_name)` references a tool that
isn't registered.

**Example message:** `Unknown tool 'frobnicate'.`

**Fix:** call `list_tools` (the MCP host's discovery path)
and pick a real tool name.

## gdb-session-error

**Trigger:** the GDB MI2 wire returned `^error` or the
underlying subprocess died mid-command (`alloy debug --tui`
flows through `core.gdb.GdbSession`).

**Example message:** `gdb-session-error: No symbol 'foo' in
current context.`

**Fix:** the message echoes GDB's own diagnostic — usually a
typo in a watched expression or a stale breakpoint
location.  If the subprocess died entirely (probe-rs
gdb-server crashed), close the screen and re-run `alloy
debug` after `probe-rs list` confirms the probe is still
attached.

**MCP tool:** none — the GDB seam stays local-only today.
