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

## family-toolchain-error

**Trigger:** generic base error for the per-MCU-family
toolchain manifest loader (`core.toolchain_registry`).
Concrete failures use one of the four sub-types below — see
those for actionable fixes.

**Example message:** typically not raised directly; sub-types
carry the specific cause.

**Fix:** branch on the sub-type's `error_type` and follow the
matching anchor in this cookbook.

**MCP tool:** `alloy.list_family_toolchain(family_id)` to
inspect what alloy-cli ships for a family.

## family-toolchain-cycle

**Trigger:** the `extends:` chain in `data/families/*.yml`
forms a cycle (`a → b → a`).  Only fires when a contributor
authors a malformed manifest pair; not user-facing.

**Example message:** `family-toolchain extends chain forms a
cycle: alpha → beta → alpha.`

**Fix:** edit the offending YAMLs so each `extends:` walks
toward a base that does NOT extend a descendant.  Cycle
detection runs at load time, so a `pytest` run will
flag the regression before merge.

**MCP tool:** none — this is bad alloy-cli data, not bad user
input.

## family-toolchain-unknown-parent

**Trigger:** a family manifest declares `extends: <id>` but
no manifest exists at `data/families/<id>.yml`.  Common when
a contributor types the parent name wrong, or removes a base
manifest without updating its children.

**Example message:** `kid.yml declares extends: 'ghost', but
no manifest exists for that family.`

**Fix:** either restore the missing parent manifest or change
the child's `extends:` to point at an existing family
(usually `arm-cortex-m` for Cortex-M children).

**MCP tool:** `alloy.list_family_toolchain` returns
`known_families` in its error envelope when called with an
unknown id — useful for picking a valid parent.

## family-toolchain-schema

**Trigger:** a manifest YAML failed JSON Schema validation
against `schema/family_toolchain_v1.json` (Draft 2020-12).
Examples: missing `core`, unknown `source`, vendor tool
without `install_docs`, unknown `capabilities` value.

**Example message:** `stm32xyz.yml failed family-toolchain
schema validation:`
``  • /required/0/source: 'homebrew' does not match …``

**Fix:** the message names the offending JSON path and the
schema rule.  See `docs/TOOLCHAIN_REGISTRY.md` for the full
field vocabulary.

**MCP tool:** none — schema failures are caught before any
tool would expose the manifest.

## family-toolchain-not-found

**Trigger:** `core.toolchain_registry.load_family(family_id)`
or `alloy.list_family_toolchain(family_id)` was called with
a family id alloy-cli does not ship a manifest for.

**Example message:** `No family manifest found for
'stm32xyz'.  Known families: arm-cortex-m, esp32, nrf52,
rp2040, stm32f4, stm32g0.`

**Fix:** pick one of the known families (the message lists
them).  To add a new family, follow the contributor walkthrough
in `docs/TOOLCHAIN_REGISTRY.md` — the data fix lands as a YAML
PR with no code changes.

**MCP tool:** the `alloy.list_family_toolchain` error envelope
returns the same `known_families` list so an LLM agent can
retry with a valid id.

## family-toolchain-installer-error

**Trigger:** generic base error for the per-MCU-family
toolchain installer (Wave 2 of toolchain-management).
Concrete failures use one of the seven sub-types below — see
those for actionable fixes.

**Example message:** typically not raised directly; sub-types
carry the specific cause.

**Fix:** branch on the sub-type's `error_type` and follow the
matching anchor in this cookbook.

**MCP tool:** `alloy.toolchain_status(family_id)` to inspect
the local store; `alloy.toolchain_install_plan(family_id)` to
preview the planned download set.

## family-toolchain-installer-checksum

**Trigger:** a downloaded artefact's SHA256 did not match the
pinned value in `data/sources/*.json`.  The streaming download
verifies bytes on the wire and refuses to finalise the file when
hashes diverge — so the corrupt / tampered tarball never lands
in the store.

**Example message:** `family-toolchain-installer-checksum:
arm-none-eabi-gcc 14.2.0 (xpack, macos-arm64): expected
abc123..., got def456...`

**Fix:**
- Re-run `alloy toolchain install` once — transient network
  flakes occasionally corrupt downloads.
- If the failure persists, inspect `data/sources/*.json` for a
  stale pin (upstream may have re-issued the release with a
  different SHA).  Run `python scripts/refresh_source_pins.py
  --apply` to regenerate the pins from upstream.
- File a bug report including the URL, expected SHA, and
  observed SHA so the maintainers can vet whether the upstream
  release was tampered with.

**MCP tool:** none — this is a download-time integrity check.

## family-toolchain-installer-download

**Trigger:** the HTTP fetch for an artefact failed (DNS
failure, 4xx/5xx, redirect to a domain not pinned in
`data/sources/`, TLS error, timeout).

**Example message:**
`family-toolchain-installer-download: HTTP 503 fetching
https://github.com/.../arm-none-eabi-gcc-14.2.0.tar.xz`

**Fix:**
- Re-run after a moment — transient HTTP errors are common.
- Behind an enterprise proxy?  Set `SSL_CERT_FILE` /
  `SSL_CERT_DIR` so stdlib `urllib` honours the proxy's
  trust roots.
- Persistent failures may indicate an upstream URL rot;
  refresh the pin file (`scripts/refresh_source_pins.py`).

**MCP tool:** `alloy.toolchain_install_plan(family_id)` to
inspect the URLs alloy-cli would otherwise hit.

## family-toolchain-installer-extract

**Trigger:** archive extraction failed — corrupt archive,
unsupported member type, or path-traversal attempt blocked by
`tarfile.data_filter`.

**Example message:**
`family-toolchain-installer-extract: refusing to write outside
extraction root: ../../etc/passwd`

**Fix:** delete `~/.local/share/alloy/tools/store/.tmp/` and
re-run `alloy toolchain install`.  If the same archive fails
twice, the upstream tarball is malformed — file a bug.

**MCP tool:** none.

## family-toolchain-installer-store-corrupt

**Trigger:** the toolchain store is in an inconsistent state.
`manifest.json` references a SHA whose `store/<sha>/` directory
is missing, or an extraction directory exists without a
matching manifest entry.  Often happens after a manual `rm -rf`
under the store.

**Example message:**
`family-toolchain-installer-store-corrupt: probe-rs 0.27.0
manifest entry has no extraction at
~/.local/share/alloy/tools/store/abc123...`

**Fix:** run `alloy toolchain install --force` to reinstall the
affected tools.  When in doubt, `alloy toolchain prune` removes
unreferenced detritus and `alloy toolchain install` re-syncs the
store with the project lockfile.

**MCP tool:** `alloy.toolchain_status(family_id)` to confirm
which tools the store is missing.

## family-toolchain-installer-version-mismatch

**Trigger:** `.alloy/toolchain.lock` pins a tool version not
present in the local store.  Raised by `alloy build / flash /
debug` before any subprocess is spawned, so the user sees the
pin/store divergence immediately.

**Example message:**
`family-toolchain-installer-version-mismatch: probe-rs 0.27.0
pinned in .alloy/toolchain.lock but store has 0.26.0.  Run
\`alloy toolchain install\`.`

**Fix:** run `alloy toolchain install` to populate the store
with the pinned version.  Alternatively, run
`alloy toolchain use probe-rs@0.26.0` to repin the lockfile to
the version you actually have installed.

**MCP tool:** `alloy.toolchain_install_plan(family_id)`.

## family-toolchain-installer-unsupported-host

**Trigger:** the active host triple
(`<os>-<arch>` derived from `platform.system()` +
`platform.machine()`) has no matching pin in any
`data/sources/*.json` for the requested tool.  Examples:
running on `linux-mips64` (no upstream binaries), or asking
Espressif tools on `linux-arm64` (Espressif does not publish
those).

**Example message:**
`family-toolchain-installer-unsupported-host: xtensa-esp-elf-gcc
14.2.0_20240906 has no pin for linux-arm64.  Supported hosts:
linux-x86_64, macos-x86_64, macos-arm64, windows-x86_64.`

**Fix:**
- Pick a different host (run on a supported machine, or build
  inside Docker / a VM with a supported triple).
- For a tool that genuinely lacks upstream binaries on your
  host, the `unsupported_hosts` field in the pin file documents
  the gap; you may need to install the tool from another source
  (system package manager, upstream build instructions).

**MCP tool:** `alloy.toolchain_status(family_id)` reports the
`state` per tool including `unsupported-host`.

## family-toolchain-installer-locked

**Trigger:** another `alloy toolchain install` (or another
mutating toolchain operation) is already running — the
advisory file lock at `<store>/.lock` is held.

**Example message:**
`family-toolchain-installer-locked: another process holds the
toolchain store lock at ~/.local/share/alloy/tools/.lock.  Wait
for it to finish and retry.`

**Fix:** wait for the other invocation to finish and re-run.
If the lock file is stale (no other alloy-cli process is
running), delete it manually: `rm
~/.local/share/alloy/tools/.lock`.

**MCP tool:** none — the lock is process-level coordination.

## onboarding-cancelled

**Trigger:** the user cancelled the onboarding wizard mid-
flight — Ctrl-C from a line prompt, the `Cancel` button in
the TUI Onboarding screen, or SIGINT during `alloy setup` /
`alloy new --install-toolchain`.  Distinct from the
`family-toolchain-*` namespace because it is a user-flow event
rather than a toolchain content failure.

**Example message:** `Onboarding cancelled by user.`  The
exception carries `.partial_outcomes` listing the tools that
DID complete before the cancel — Wave-2's per-tool atomicity
ensures those installs are consistent.

**Fix:**
- Re-run the wizard (`alloy setup`, `alloy new
  --install-toolchain`, or `alloy ui` → Onboarding screen) —
  the manager is idempotent so already-installed tools are
  recognised as no-ops.
- Or run `alloy toolchain install` directly, which finishes
  the install without the wizard prompts.

**MCP tool:** not applicable — MCP callers cannot mid-cancel
`alloy.toolchain_apply_install_plan`; that tool runs to
completion or fails with a typed
`family-toolchain-installer-*` envelope.

## family-toolchain-probe-error

**Trigger:** umbrella class for every Wave-4 probe failure.
Sub-classes (`family-toolchain-probe-not-found`,
`family-toolchain-probe-not-attached`,
`family-toolchain-probe-multiple-attached`,
`family-toolchain-probe-unauthorised`) carry the specific
context.  Catch this base when you want to handle "anything
went wrong with the probe-side."

**Fix:** dispatch on the specific sub-type — see the dedicated
sections below.

**MCP tool:** raised by `probe_reset`, `probe_erase`,
`probe_erase_plan`, `probe_monitor_open`.

## family-toolchain-probe-not-found

**Trigger:** the project's `.alloy/toolchain.lock` pins
`probe-rs` (or `openocd`) but the binary is missing from the
local store — typically after `alloy toolchain prune` removed
it, or after a manual edit to the store.

**Example message:** `probe-rs binary missing from store; run
\`alloy toolchain install\` to repopulate.`

**Fix:**
- Re-run `alloy toolchain install` (the lockfile pins are
  honoured; the manager re-fetches the missing binaries).
- If the lockfile itself is corrupt, delete
  `.alloy/toolchain.lock` and run `alloy toolchain install`
  to regenerate it.

**MCP tool:** raises the same envelope from `probe_reset`,
`probe_erase`, `probe_monitor_open`.

## family-toolchain-probe-not-attached

**Trigger:** `alloy reset` / `alloy erase` / `alloy monitor`
ran but no probe is USB-attached (or the kernel hasn't enumerated
it yet).

**Example message:** `No probe attached; plug in your debugger
and try again.`

**Fix:**
- Plug the probe in, wait a second, retry.
- On Linux, verify udev rules are installed (`alloy doctor`
  surfaces the rules path Wave-2 generated).
- On macOS, check that the OS sees the probe via `system_profiler
  SPUSBDataType | grep -i jlink` (or similar).

**MCP tool:** `probe_reset`, `probe_erase`, `probe_monitor_open`
all surface this envelope when no probe is attached.

## family-toolchain-probe-multiple-attached

**Trigger:** more than one probe is USB-attached and the user
did not pass `--probe`.  The orchestrator refuses to guess.

**Example message:** `Multiple probes attached; pass
--probe vid:pid:serial to disambiguate.`  The error carries
`.detected` listing every probe (vid, pid, serial, kind).

**Fix:**
- Pass the `--probe` selector with the desired probe's
  `vid:pid:serial` triple (the message lists every detected
  probe).
- Or unplug the probes you don't need.

**MCP tool:** the envelope carries `detected_probes` so the
agent can surface the list to the user and re-call the tool
with the chosen `probe`.

## family-toolchain-probe-unauthorised

**Trigger:** the detected probe is vendor-only — proprietary
J-Link firmware, ST-Link with locked firmware, or another probe
whose driver alloy-cli cannot legally redistribute.  The
orchestrator NEVER auto-invokes vendor tools.

**Example message:** `Vendor-only probe detected; install
J-Link Commander to reset / erase the target.`  The error
carries `.vendor_tool` (human-readable name) and
`.install_doc_url`.

**Fix:**
- Install the vendor utility named in the message; invoke it
  manually for reset / erase / monitor.
- Or use a non-vendor-locked probe (CMSIS-DAP, generic
  ST-Link with open firmware) so probe-rs can drive it.

**MCP tool:** the envelope carries `vendor_tool` +
`install_doc_url` so the agent can surface the install link
to the user.

## family-toolchain-erase-error

**Trigger:** umbrella class for every Wave-4 erase failure.
Sub-classes (`family-toolchain-erase-aborted`,
`family-toolchain-erase-unsupported-region`,
`family-toolchain-erase-confirmation-required`,
`family-toolchain-erase-probe-failed`) carry the specific
context.  Catch this base when you want to handle "anything
went wrong with the erase."

**Fix:** dispatch on the specific sub-type — see the dedicated
sections below.

**MCP tool:** raised by `probe_erase_plan` (for region
validation) and `probe_erase` (for execution failures).

## family-toolchain-erase-aborted

**Trigger:** the user answered N (or anything that wasn't `y`)
at the `alloy erase` confirmation prompt — or the CLI refused
to proceed in a non-TTY without `--auto` / `--yes`.

**Example message:** `Erase aborted by user.`

**Fix:**
- If you really meant to erase, re-run with `--auto` (or `--yes`)
  in non-TTY contexts; in a TTY, answer `y` at the prompt.
- If you didn't mean to erase, you're done — the chip is
  untouched.

**MCP tool:** never surfaces this envelope from `probe_erase`
because MCP agents have no prompt path.  The MCP equivalent
is `family-toolchain-erase-confirmation-required`.

## family-toolchain-erase-unsupported-region

**Trigger:** `alloy erase --region <name>` where `<name>` is not
a flash region the device IR declares.  The orchestrator carries
`.known_regions` listing the regions the IR DOES expose.

**Example message:** `Unknown region 'boot-rom'; known regions:
bootloader, appslot-a, appslot-b.`

**Fix:**
- Use one of the names listed in the error message.
- Or pass a literal `0xBASE-0xEND` range when the IR has no
  named regions for your device.
- If your device's IR is missing region aliases that should
  exist, file an upstream IR fix in `alloy-devices-yml`.

**MCP tool:** `probe_erase_plan` and `probe_erase` both surface
the envelope with `known_regions` populated.

## family-toolchain-erase-confirmation-required

**Trigger:** an MCP agent called `alloy.probe_erase` without
passing `confirm=true`.  The two-phase pattern requires the
agent to call `probe_erase_plan` first, surface the plan to the
user, get explicit confirmation, then call `probe_erase` with
`confirm=true`.

**Example message:** `probe_erase requires confirm=true; call
probe_erase_plan first to preview.`

**Fix:**
- Update the agent's tool-call sequence to follow the two-phase
  pattern: preview → confirm → apply.
- The agent SHOULD render the plan to the user verbatim before
  calling `probe_erase` with `confirm=true`.

**MCP tool:** raised by `probe_erase` itself.  Never raised by
the CLI (which uses an interactive prompt instead).

## family-toolchain-erase-probe-failed

**Trigger:** the backend (probe-rs / openocd) returned non-zero
during the erase.  Could indicate a hardware fault, a wrong
target chip in the lockfile, or a probe that lost USB power.

**Example message:** `Probe-side erase failed (returncode=2):
probe-rs: Could not connect to target.`  The error carries
`.stderr` + `.returncode`.

**Fix:**
- Check the probe's USB cable + power.
- Verify the chip in `alloy.toml`'s `[chip]` matches the
  hardware (a stm32g0 lockfile won't erase a stm32f4 board).
- Run `alloy doctor` to confirm the lockfile-pinned probe-rs
  matches the host triple.

**MCP tool:** the envelope carries `stderr` + `returncode` so
the agent can surface backend output to the user.

## probe-operation-cancelled

**Trigger:** the user pressed Ctrl+] in `alloy monitor` (the
graceful disconnect key, mirroring `screen` / telnet) — OR an
MCP `probe_monitor_*` session timed out (5 minutes idle) — OR
the agent called `probe_monitor_close` then tried to `poll` /
`close` again.

**Example message:** `Closed monitor session.  124 bytes
captured over 47.2s.`  The exception carries
`.duration_ms`, `.bytes_captured`, `.last_line` so the CLI can
summarise.

**Fix:**
- This is NOT an error — it's a graceful disconnect.  The CLI
  exits 0; the MCP tool returns a closed session envelope.
- Open a new session if you need to keep watching the log.

**MCP tool:** raised by `probe_monitor_poll` /
`probe_monitor_close` after a session ended.
