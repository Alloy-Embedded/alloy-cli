# Recovery (Wave 4)

Wave 4 closes the user-facing arc of the toolchain-management track
by giving the firmware developer the three primitives every embedded
engineer reaches for during normal hardware bring-up:

- `alloy reset` — non-destructive CPU / nRST reset.
- `alloy erase` — flash erase with a TTY confirmation gate.
- `alloy monitor` — live UART / RTT log viewer.

All three dispatch through a single shared orchestrator
(`core.probe_orchestrator`) that owns probe selection, binary
resolution from `.alloy/toolchain.lock`, and the typed-error
vocabulary.  The CLI, the TUI `MonitorScreen`, and four MCP tools
(`probe_reset`, `probe_erase_plan`, `probe_erase`,
`probe_monitor_{open,poll,close}`) all route through that one seam.

Cross-links:

- [TOOLCHAIN_REGISTRY.md](TOOLCHAIN_REGISTRY.md) — Wave 1: per-MCU-
  family manifest format.
- [TOOLCHAIN_INSTALLER.md](TOOLCHAIN_INSTALLER.md) — Wave 2:
  content-addressed store + lockfile.
- [TOOLCHAIN_ONBOARDING.md](TOOLCHAIN_ONBOARDING.md) — Wave 3:
  install orchestration.
- [QUICKSTART.md](QUICKSTART.md) — five-minute walkthrough that
  uses these flows.
- [ERROR_COOKBOOK.md](ERROR_COOKBOOK.md) — every typed error_type
  the orchestrator can surface.

---

## The three commands (and the MCP write-side)

| Situation | Reach for |
|---|---|
| "My firmware is stuck — reset it." | `alloy reset` |
| "I want to leave the core halted for the debugger." | `alloy reset --halt-after-reset` |
| "I bricked the chip; wipe everything." | `alloy erase` |
| "Erase only the bootloader region." | `alloy erase --region bootloader` |
| "Watch the UART log." | `alloy monitor --port /dev/cu.usbmodem1234` |
| "I'm an LLM agent on the MCP transport." | `alloy.probe_reset` (safe) / `alloy.probe_erase_plan → probe_erase(confirm=true)` (mutating) / `alloy.probe_monitor_{open,poll,close}` (session) |

### `alloy reset`

```sh
alloy reset                          # soft CPU reset (default)
alloy reset --hard                   # pulses nRST line via probe-rs
alloy reset --halt-after-reset       # leave core halted for debugger
alloy reset --probe 0483:374b:AAA    # explicit probe selector
```

Lockfile-aware: the probe-rs binary comes from
`.alloy/toolchain.lock` when present; falls back to PATH otherwise.
The success panel summarises the probe id, reset method, and elapsed
milliseconds.

### `alloy erase`

```sh
alloy erase                                      # TTY: prompt fires; default N
alloy erase --auto                               # CI: bypass prompt
alloy erase --yes                                # alias for --auto
alloy erase --region bootloader --auto           # IR alias (when manifest declares it)
alloy erase --region 0x08000000-0x08010000 --auto   # literal range
```

Two safety gates:

1. **TTY prompt** (default): renders the plan + chip id + total bytes
   then asks `Continue? [y/N]`.  Default N — anything other than `y`
   / `yes` raises `family-toolchain-erase-aborted`.
2. **`--auto` / `--yes`**: required in non-TTY contexts (CI / pipe).
   Without one, the command refuses to run rather than block on
   STDIN nobody can answer.

### `alloy monitor`

```sh
alloy monitor --port /dev/cu.usbmodem1234        # explicit port
alloy monitor --port /dev/... --baud 921600      # explicit baud
alloy monitor --port /dev/... --mode rtt         # probe-rs RTT
alloy monitor --port /dev/... --ansi             # pass-through ANSI
```

Press `Ctrl+]` to disconnect; the command reports byte count,
duration, and last line on close.  Exit code is 0 (graceful
disconnect is not a failure).

The OS-level serial path (`/dev/cu.usbmodem*`) always requires
`--port` because USB enumeration is host-specific.  The baud rate
is autodetected from `alloy.toml`'s console UART peripheral when
available; falls back to 115200.

### MCP `alloy.probe_*`

LLM agents follow the **two-phase** pattern for destructive ops:

```python
# Reset is safe — no preview required.
report = client.call("probe_reset", method="soft")

# Erase requires the preview-then-confirm dance.
plan = client.call("probe_erase_plan", regions=["bootloader"])
# Surface plan to the user; get explicit confirmation.
report = client.call("probe_erase", regions=["bootloader"], confirm=True)

# Monitor sessions are session-style.
session = client.call("probe_monitor_open", port="/dev/cu.usb1234")
sid = session["session_id"]
while True:
    chunk = client.call("probe_monitor_poll", session_id=sid)
    if chunk["closed"]:
        break
    if chunk["new_bytes"]:
        print(chunk["new_bytes"], end="")
client.call("probe_monitor_close", session_id=sid)
```

Calling `probe_erase` without `confirm=true` raises
`family-toolchain-erase-confirmation-required`.  Sessions auto-close
after 5 minutes of poll inactivity so a crashed agent does not leak
threads.

---

## The shared orchestrator API

Every recovery surface dispatches through one module:

```python
from alloy_cli.core.probe_orchestrator import (
    select_probe,
    reset_target,
    plan_erase,
    execute_erase,
    open_monitor,
)

probe = select_probe(hint=None, project_root=Path.cwd())
report = reset_target(probe, method="soft", halt_after=False)

plan = plan_erase(probe, regions=["bootloader"], project_root=Path.cwd())
report = execute_erase(probe, plan)

bytes_seen = open_monitor(
    probe,
    port=Path("/dev/cu.usbmodem1234"),
    baud=115200,
    mode="raw",
    on_event=on_monitor_event,
)
```

### `Probe` Protocol + `FakeProbe`

The orchestrator defines a `Probe` Protocol that backends implement.
Wave 4 ships:

- `_RealProbeRsProbe` — subprocess wrapper around the lockfile-pinned
  `probe-rs`.  Production callers reach it via `real_probe_for(...)`.
- `FakeProbe` — test seam mirroring Wave 2's `FakeDownloader`
  pattern.  Records every `reset` / `erase` / `monitor` call;
  emits scripted `MonitorEvent`s.  Tests inject typed failures via
  `fail_next_reset(...)` / `fail_next_erase(...)`.

### `MonitorEvent` (sealed union)

The `on_event` callback receives one of:

- `MonitorOpened(probe, port, baud, mode, started_at_ms)` — session
  is live; bytes will start arriving.
- `MonitorBytes(chunk, timestamp_ms)` — a chunk of raw bytes from
  the target.  UI shells decode + render.
- `MonitorClosed(duration_ms, bytes_captured, last_line)` — session
  ended (cleanly or via timeout).

### `MonitorSessionTable`

The MCP `probe_monitor_*` triplet shares a process-global session
table (`alloy_cli.mcp.tools._MONITOR_SESSIONS`).  Sessions are
keyed on UUID; each owns a thread-safe byte buffer + close flag.
Idle sessions auto-close after 5 minutes of poll inactivity.

---

## Vendor-probe contract

Vendor-only probes — proprietary J-Link firmware, ST-Link with
locked firmware — surface as
`family-toolchain-probe-unauthorised` with the vendor utility name
+ install_doc URL.  The orchestrator NEVER auto-invokes the vendor
tool.  Every surface honours this:

- `alloy reset` — exits non-zero, names the vendor utility inline.
- `alloy erase` — same as reset (probe selection happens before
  the safety gate).
- `alloy monitor` — RTT mode raises the typed envelope; raw mode
  doesn't trigger it (no probe selection in raw mode).
- TUI `MonitorScreen` — surfaces the error via a Toast.
- MCP `probe_*` tools — typed envelope with `vendor_tool` +
  `install_doc_url` keys in `detail`.

To opt a specific probe into vendor-only mode set
`ALLOY_PROBE_VENDOR_ONLY=<vid:pid>` (comma-separated for multiple
entries).  The default heuristic is conservative — common probes
are treated as drivable.

---

## Cancellation contract

| Surface | Trigger | Result |
|---|---|---|
| CLI `alloy monitor` | Ctrl+] | `ProbeOperationCancelledError`, exit 0 |
| TUI `MonitorScreen` | Ctrl+] / Esc | `dismiss(MonitorSummary(...))` |
| MCP `probe_monitor_*` | 5-min idle timeout | next `poll` raises `probe-operation-cancelled` |

The cancellation event carries `bytes_captured`, `duration_ms`, and
`last_line` so the CLI can render a one-line summary:

```
Closed monitor session.  124 bytes captured over 47.2s.
Last line: 'boot complete'
```

See [ERROR_COOKBOOK.md#probe-operation-cancelled](
ERROR_COOKBOOK.md#probe-operation-cancelled) for the full taxonomy.

---

## Error vocabulary

| `error_type` | Surfaced when |
|---|---|
| `family-toolchain-probe-not-found` | Lockfile pins probe-rs but the binary is missing from the store. |
| `family-toolchain-probe-not-attached` | No probe USB-attached. |
| `family-toolchain-probe-multiple-attached` | More than one probe; `--probe` selector required.  Carries `.detected`. |
| `family-toolchain-probe-unauthorised` | Vendor-only probe.  Carries `.vendor_tool` + `.install_doc_url`. |
| `family-toolchain-erase-aborted` | TTY prompt answered N (or anything not affirmative). |
| `family-toolchain-erase-unsupported-region` | `--region <name>` not in device IR.  Carries `.known_regions`. |
| `family-toolchain-erase-confirmation-required` | MCP agent called `probe_erase` without `confirm=true`. |
| `family-toolchain-erase-probe-failed` | Backend (probe-rs / openocd) returned non-zero.  Carries `.stderr` + `.returncode`. |
| `probe-operation-cancelled` | Graceful Ctrl+] disconnect / monitor session timeout.  Carries `.duration_ms` + `.bytes_captured` + `.last_line`. |

Every entry has a cookbook anchor in
[ERROR_COOKBOOK.md](ERROR_COOKBOOK.md):

- [`family-toolchain-probe-not-found`](ERROR_COOKBOOK.md#family-toolchain-probe-not-found)
- [`family-toolchain-probe-not-attached`](ERROR_COOKBOOK.md#family-toolchain-probe-not-attached)
- [`family-toolchain-probe-multiple-attached`](ERROR_COOKBOOK.md#family-toolchain-probe-multiple-attached)
- [`family-toolchain-probe-unauthorised`](ERROR_COOKBOOK.md#family-toolchain-probe-unauthorised)
- [`family-toolchain-erase-aborted`](ERROR_COOKBOOK.md#family-toolchain-erase-aborted)
- [`family-toolchain-erase-unsupported-region`](ERROR_COOKBOOK.md#family-toolchain-erase-unsupported-region)
- [`family-toolchain-erase-confirmation-required`](ERROR_COOKBOOK.md#family-toolchain-erase-confirmation-required)
- [`family-toolchain-erase-probe-failed`](ERROR_COOKBOOK.md#family-toolchain-erase-probe-failed)
- [`probe-operation-cancelled`](ERROR_COOKBOOK.md#probe-operation-cancelled)

---

## Where the code lives

- `src/alloy_cli/core/probe_orchestrator.py` — shared walker
  (UI-free).  Contains `Probe` Protocol, `FakeProbe`,
  `_RealProbeRsProbe`, `MonitorSessionTable`, plus the public
  `select_probe` / `reset_target` / `plan_erase` /
  `execute_erase` / `open_monitor` / `real_probe_for` functions.
- `src/alloy_cli/core/errors.py` — nine new typed errors registered
  under the Wave-4 error_type vocabulary.
- `src/alloy_cli/commands/reset.py` — `alloy reset` Click command.
- `src/alloy_cli/commands/erase.py` — `alloy erase` Click command.
- `src/alloy_cli/commands/monitor.py` — `alloy monitor` Click
  command.
- `src/alloy_cli/tui/screens/monitor.py` — TUI `MonitorScreen`.
- `src/alloy_cli/mcp/tools.py` — six new MCP probe tools wired
  through the orchestrator.

A regression test (`tests/test_probe_orchestrator_contract.py`)
enforces "every entry point routes through `probe_orchestrator`":
any new file under `commands/`, `tui/`, or `mcp/` that calls
`flash.detect_probes` directly must also import from
`probe_orchestrator` or be explicitly grandfathered.
