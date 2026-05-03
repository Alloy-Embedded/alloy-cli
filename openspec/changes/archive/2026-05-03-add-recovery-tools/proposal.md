## Why

Waves 1–3 took the firmware developer from `pip install alloy-cli` to a
flashed Nucleo through one shared install pipeline.  But once the
firmware lands on the chip, the user pivots to bring-up: reset the
target, erase the flash to recover from a brick, and read serial logs
to verify behaviour.  Today every alloy-cli user falls back to
hand-rolled `probe-rs reset`, vendor erase utilities, and `screen
/dev/cu.usbmodem*` on a separate terminal.  Wave 4 closes the
user-facing arc by giving the developer the three recovery primitives
they need — `alloy reset`, `alloy erase`, `alloy monitor` — welded
into the same lockfile-aware probe / binary resolution pipeline,
typed-error vocabulary, and MCP / TUI surfaces Waves 1–3 shipped.
Without Wave 4 the user has to leave alloy-cli the moment something
goes wrong on the hardware, which breaks the "one tool from install
to bring-up" promise.

## What Changes

- New `alloy reset` Click command — soft (CPU) / hard (nRST) reset
  with optional `--halt-after-reset`, lockfile-aware probe-rs /
  openocd dispatch, `--probe <vid:pid:serial>` selector matching
  `alloy flash`'s semantics.
- New `alloy erase` Click command — chip-wide or `--region <name>`
  partial erase with two safety gates (TTY confirmation by default;
  `--auto` / `--yes` for CI).  Resolves region aliases from the
  device IR's flash bank descriptors.  Surfaces typed
  `family-toolchain-erase-{aborted,unsupported-region,
  confirmation-required,probe-failed}` errors.
- New `alloy monitor` Click command — live UART / RTT log viewer.
  Auto-detects the debug UART from `alloy.toml`'s `[uart].debug`
  config; `--port` / `--baud` overrides; `--mode raw|rtt`.  Press
  Ctrl+] to disconnect; the session reports byte count + duration
  + last-line-seen timestamp.
- New `core.probe_orchestrator` module — UI-free single seam where
  `alloy flash` (existing), `alloy reset`, `alloy erase`, future
  `alloy debug`, and the new MCP probe tools all dispatch.  Owns
  probe selection, binary resolution from `.alloy/toolchain.lock`,
  typed error vocabulary, subprocess argv assembly.
- New `Probe` Protocol + `FakeProbe` test seam — same pattern as
  the Wave-2 `Downloader` Protocol so the orchestrator + every
  entry point can be tested without real hardware.
- New `OnboardingCancelledError` sibling: `ProbeOperationCancelledError`
  for `alloy monitor` Ctrl+] disconnects (carries duration + byte
  count) so `commands/monitor.py` can summarise cleanly.
- Four new MCP write tools wired through the probe orchestrator:
  `alloy.probe_reset` (idempotent); `alloy.probe_erase_plan` (read-
  only preview); `alloy.probe_erase` (mutating, requires `confirm=
  true` after the plan); `alloy.probe_monitor_open` (session-style;
  returns a session id the agent polls for new lines and closes).
- Extended TUI `DebugScreen` (Wave-1 placeholder) with a Reset /
  Erase / Open Monitor action group.  New TUI `MonitorScreen` —
  Textual `RichLog` viewer with Ctrl+] modal close.
- Stable error-type vocabulary registered in
  `tests/test_errors_uniqueness.py`:
  `family-toolchain-probe-{not-found,not-attached,
  multiple-attached,unauthorised}` and
  `family-toolchain-erase-{aborted,unsupported-region,
  confirmation-required,probe-failed}`.
- Cookbook anchors for every new error_type so
  `scripts/check_error_cookbook.py` stays green.
- New `docs/RECOVERY.md` covering the three commands + the probe
  orchestrator API + the shared error taxonomy + cross-links to
  Waves 1–3 docs.  QUICKSTART addendum showing `alloy reset` /
  `alloy monitor` after the build/flash steps.  System prompt
  update so LLM agents know the safety gating on `probe_erase`.
- Cheatsheet regen so the new verbs land in `docs/CHEATSHEET.md`.

## Capabilities

### New Capabilities

- `recovery-tools`: shared probe orchestrator + the three new
  recovery verbs (`alloy reset`, `alloy erase`, `alloy monitor`) +
  the four MCP probe tools + the typed error vocabulary +
  `RECOVERY.md`.

### Modified Capabilities

- `cli-surface`: registers the three new Click commands; `--probe`
  selector contract clarified (matches `alloy flash`'s vid:pid:serial
  shape); `--auto` / `--yes` semantics on `alloy erase` mirror
  Wave-3's `alloy new` / `alloy setup` confirmation contract.
- `mcp-surface`: four new tools land in the registry +
  `_PARAM_SCHEMA`.  `probe_erase` is the second mutating tool to
  follow the two-phase pattern (after Wave-3's
  `toolchain_apply_install_plan`).
- `tui-experience`: Wave-1 `DebugScreen` placeholder gains a real
  action group; new `MonitorScreen` registered via
  `register_screen("monitor", …)` so the command palette discovers
  it.
- `developer-experience`: new `RECOVERY.md` + QUICKSTART addendum
  + cheatsheet regen.  Doc regression test (mirrors Wave 3's
  `test_toolchain_onboarding_doc.py`) ensures every new error_type,
  every new command, and every cookbook cross-link stays present.

## Impact

- **Affected modules**: `src/alloy_cli/core/probe_orchestrator.py`
  (NEW), `src/alloy_cli/core/errors.py` (new error classes),
  `src/alloy_cli/commands/{reset,erase,monitor}.py` (NEW),
  `src/alloy_cli/main.py` (registers the three new verbs),
  `src/alloy_cli/mcp/tools.py` (four new handlers),
  `src/alloy_cli/tui/screens/debug.py` (action group),
  `src/alloy_cli/tui/screens/monitor.py` (NEW screen).
- **Lockfile contract**: read-only consumer of
  `.alloy/toolchain.lock`'s `probe-rs` / `openocd` pins.  No
  changes to Wave-2's lockfile schema.
- **Hardware deps**: needs a real probe to exercise end-to-end;
  every test path uses the `FakeProbe` Protocol seam.
- **Vendor contract**: `family-toolchain-probe-unauthorised` row
  surfaces when a vendor-only probe (proprietary J-Link, ST-Link
  with locked firmware) is detected — the orchestrator NEVER
  auto-invokes the vendor tool, just names it.
- **Test count**: an estimated +60 tests (orchestrator, three
  commands, four MCP tools, doc regression, error uniqueness).
  Total suite expected to land near 1000 passing after Wave 4.
- **Out of scope**: `alloy gdb` interactive session (Wave-1
  placeholder stays); DFU / mass-storage updates; bidirectional
  RTT (Wave 4 is read-only RTT).
