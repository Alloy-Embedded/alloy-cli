## Context

Wave 4 closes the user-facing arc of the toolchain-management track.
Waves 1–3 stand up the install pipeline: per-MCU-family manifests
(Wave 1), content-addressed store + lockfile (Wave 2), and the
five user-facing onboarding flows that all dispatch through one
shared orchestrator (Wave 3).  The lockfile already pins the
``probe-rs`` (and, on platforms that need it, ``openocd``) binaries
the user installed.  ``alloy flash`` already resolves them through
the lockfile-aware flash path Wave 2 shipped.

But the moment the firmware is on the chip, the user pivots to
bring-up: reset the target after a stuck loop, erase the flash to
recover from a brick, monitor the UART to see what the program
prints.  Today every alloy-cli user falls back to:

```sh
$(probe-rs path) reset --chip stm32g0
$(probe-rs path) erase --chip stm32g0
screen /dev/cu.usbmodem1234 115200
```

Three different binaries, three different argv conventions, no
typed errors, no MCP integration, no TUI integration.  This is
exactly the surface Wave 3's `toolchain_orchestrator` solved for
installs, and Wave 4 mirrors that solution for probe operations.

Stakeholders:
- **Firmware developers** — the daily-driver users.  They expect
  the same "one tool, no PATH munging" UX Wave 3 delivers for
  installs.
- **CI / scripted bootstrap** — needs `--auto` / `--yes` flags on
  destructive operations (erase) so non-interactive runs never
  hang on a prompt.
- **LLM agents on MCP** — need typed JSON envelopes for every
  outcome and a two-phase pattern for destructive ops (mirrors
  Wave 3's `toolchain_install_plan` → `toolchain_apply_install_plan`).
- **TUI users** — expect Reset / Erase actions in the existing
  `DebugScreen` placeholder and a real `MonitorScreen` they can
  reach from `Ctrl+P`.

Constraints inherited from Waves 1–3:
- ``core/`` modules stay UI-free.  No Click, Rich, Textual,
  ``input()``, ``sys.stdin`` — the `tests/test_..._contract.py`
  AST guards enforce this.
- Every typed error gets an `error_type` string registered in
  `tests/test_errors_uniqueness.py` and a cookbook anchor in
  `docs/ERROR_COOKBOOK.md`.
- Every entry point dispatches through one shared orchestrator —
  AST contract tests ensure no entry point reimplements the walk.
- Frozen + slots dataclasses for typed events; JSON-friendly
  fields so MCP serialisation stays trivial.
- Tests use a Protocol-based seam (`Probe`) with a `FakeProbe` —
  the same shape Wave 2's `Downloader` Protocol uses.

## Goals / Non-Goals

**Goals:**

1. Three new user-facing verbs (`alloy reset`, `alloy erase`,
   `alloy monitor`) with the same UX consistency Wave 3
   established for installs.
2. A single shared probe orchestrator (`core.probe_orchestrator`)
   every entry point — CLI, TUI, MCP — dispatches through.  No
   duplication of probe selection, binary resolution, or argv
   assembly.
3. Hard safety gating on `alloy erase` (destructive op): TTY
   prompt by default; `--auto` / `--yes` for non-interactive;
   typed `family-toolchain-erase-confirmation-required` error
   when the MCP agent forgets the two-phase preview.
4. Lockfile-aware probe-rs / openocd dispatch: the binaries come
   from `.alloy/toolchain.lock`; the orchestrator surfaces a
   typed error when no pin matches and points the user at
   `alloy toolchain install`.
5. Vendor-probe contract: vendor-only probes (proprietary
   J-Link, ST-Link with locked firmware) surface as
   info-severity rows naming the vendor tool — never auto-invoked.
6. Read-only RTT support in `alloy monitor --mode rtt` (one-way;
   bidirectional deferred to Wave 5).

**Non-Goals:**

- `alloy gdb` interactive GDB session orchestration (Wave 1's
  placeholder stays in `commands/debug.py`).
- DFU / mass-storage firmware update via `alloy bootloader` /
  `alloy dfu`.
- Bidirectional RTT (the `alloy monitor` send-bytes-back path
  is read-only Wave 4; full duplex is Wave 5).
- Probe firmware upgrades (`probe-rs upgrade`) — out of scope.
- Vendor-tool dispatch.  We never auto-invoke STM32CubeProgrammer
  / nrfjprog / J-Link.  We name them and link to install_doc URLs.

## Decisions

### D1: Probe orchestrator is UI-free, mirrors `toolchain_orchestrator`

```python
# core/probe_orchestrator.py — public API surface

@dataclass(frozen=True, slots=True)
class ProbeIdentity:
    vid: str
    pid: str
    serial: str
    kind: str        # "stlink" | "jlink" | "cmsis-dap" | "esp-jtag" | …
    vendor_only: bool

@dataclass(frozen=True, slots=True)
class ResetReport:
    probe: ProbeIdentity
    method: str      # "soft" | "hard"
    halt_after: bool
    duration_ms: int

@dataclass(frozen=True, slots=True)
class EraseRegion:
    name: str        # "all" | "bootloader" | "appslot-a" | "0x0800_0000-0x0801_0000"
    base: int
    size: int

@dataclass(frozen=True, slots=True)
class ErasePlan:
    probe: ProbeIdentity
    regions: tuple[EraseRegion, ...]
    total_bytes: int

@dataclass(frozen=True, slots=True)
class EraseReport:
    probe: ProbeIdentity
    regions: tuple[EraseRegion, ...]
    total_bytes_erased: int
    duration_ms: int

@dataclass(frozen=True, slots=True)
class MonitorEvent:
    """Sealed union: one of MonitorOpened, MonitorBytes, MonitorClosed."""
    ...

# Protocol every backend implements (probe-rs, openocd, FakeProbe)
class Probe(Protocol):
    @property
    def identity(self) -> ProbeIdentity: ...
    def reset(self, *, method: str, halt_after: bool) -> ResetReport: ...
    def erase(self, regions: Sequence[EraseRegion]) -> EraseReport: ...
    def monitor(self, *, port: Path | None, baud: int, mode: str,
                on_event: Callable[[MonitorEvent], None]) -> int: ...

# Orchestrator-level entry points
def select_probe(*, hint: str | None, project_root: Path | None) -> Probe: ...
def reset_target(probe: Probe, *, method: str = "soft", halt_after: bool = False) -> ResetReport: ...
def plan_erase(probe: Probe, *, regions: Sequence[str] | None = None,
               project_root: Path | None = None) -> ErasePlan: ...
def execute_erase(probe: Probe, plan: ErasePlan) -> EraseReport: ...
def open_monitor(probe: Probe, *, port: Path | None = None, baud: int = 115200,
                 mode: str = "raw", on_event: Callable[[MonitorEvent], None]) -> int: ...
```

The orchestrator owns:
- Probe selection (single-attached heuristic; `--probe` flag
  override; multiple-attached → typed error listing them).
- Binary resolution from `.alloy/toolchain.lock` (probe-rs path
  for `kind=stlink/cmsis-dap/jlink`; openocd path for
  `kind=esp-jtag`).
- Subprocess argv assembly per backend.
- Typed error vocabulary.

Every entry point provides its own UI (Rich progress for CLI,
Textual `RichLog` for TUI, JSON for MCP) but routes through these
public functions.

**Alternatives considered:**

- *One God object that owns every probe operation*. Rejected:
  doesn't compose with the per-backend Protocol pattern; harder
  to fake.
- *Reuse Wave 2's `tool_sources.adapter_for`*. Rejected: tool
  sources resolve install artefacts (URL + sha + size), probes
  resolve runtime devices.  Different lifecycles, different
  failure modes.

### D2: `Probe` Protocol + `FakeProbe` mirrors Wave 2's `Downloader` shape

A `FakeProbe` records every call (`reset_calls`, `erase_calls`,
`monitor_sessions`) and emits scripted `MonitorEvent`s.  Every
test path uses it — no real hardware in CI.

A single `_RealProbeRsProbe` implementation wraps a subprocess
seam.  Tests can swap the subprocess runner via the existing
`core.process.CommandRunner` (the same seam Wave 2's manager uses).

**Alternatives considered:**

- *MagicMock-based testing*. Rejected: leaks attribute access
  errors; doesn't pin the contract.
- *Real probe-rs SDK Python bindings*. Rejected: adds a heavy
  dependency the lockfile already covers via the binary; we
  shell out to the same probe-rs the user installed.

### D3: Two-phase pattern for `alloy erase` mirrors Wave 3's `toolchain_apply_install_plan`

CLI surface:

```sh
alloy erase                       # prompt fires (default N), TTY required
alloy erase --auto                # CI shape: no prompt
alloy erase --region bootloader   # alias resolved from device IR
alloy erase --region 0x08000000-0x08010000   # explicit address range
```

MCP surface:

```python
plan = client.call("probe_erase_plan")             # read-only preview
# agent surfaces plan["regions"] + plan["total_bytes"]
report = client.call("probe_erase", confirm=True)  # mutating; refuses without confirm=True
```

The CLI's interactive prompt and the MCP's `confirm=True` are
the same logical safety gate — different UI shells.  Without
either, the orchestrator raises
`FamilyToolchainEraseConfirmationRequiredError`.

**Alternatives considered:**

- *Always erase, no prompt*. Rejected: hostile UX; one
  Tab-completion mistake bricks the chip.
- *--force flag instead of --auto*. Rejected: collides with the
  existing semantic of "skip atomicity checks" elsewhere; `--auto`
  matches Wave 3's `alloy setup --auto` / `alloy new --auto`.

### D4: `--region` aliases come from device IR's flash bank descriptors

`alloy.toml`'s `[chip]` resolves to a device IR via Wave 1's
`alloy_cli.core.ir.load_device(...)`.  The IR's flash bank
descriptors carry named regions (when the manufacturer ships
them): `bootloader`, `appslot-a`, `appslot-b`, `userdata`.  The
orchestrator's `plan_erase` accepts:

- `None` → erase everything (chip-wide).
- A list of region names → resolve each via the IR; raise
  `family-toolchain-erase-unsupported-region` when one is unknown.
- A list of explicit `0xBASE-0xEND` ranges → pass through.

When the IR has no named regions, `--region <name>` always raises
`unsupported-region` and the message lists the device that's
missing the metadata so the user can file an upstream IR fix.

**Alternatives considered:**

- *Hardcoded region tables per family*. Rejected: doesn't scale;
  Wave 1 already owns the IR vocabulary.
- *Sector-number flag (`--sectors 0-3`)*. Rejected: error-prone
  (sector numbering varies per family); ranges are the universal
  unit.

### D5: `alloy monitor` Ctrl+] graceful close + `ProbeOperationCancelledError`

Pressing Ctrl+] in `alloy monitor` raises
`ProbeOperationCancelledError(error_type=
"probe-operation-cancelled", duration_ms=N, bytes_captured=M)`.
The CLI catches it and prints a clean summary:

```
Closed monitor session.  124 bytes captured over 47.2s.
Last line: "boot complete\n"
```

This mirrors Wave 3's `OnboardingCancelledError` exit-130
contract — for `alloy monitor` we exit 0 (graceful disconnect is
not a failure), but the typed event still surfaces.

**Alternatives considered:**

- *Re-use SIGINT*. Rejected: SIGINT typically propagates from
  the parent shell; many users want Ctrl+C to actually kill alloy
  if monitor wedges.  Ctrl+] is the standard "leave but don't
  abort" key (telnet, screen).
- *Only --duration N flag, no interactive close*. Rejected:
  takes away the streaming UX completely.

### D6: TUI `MonitorScreen` is a session viewer, not a terminal emulator

The screen renders a `RichLog` of incoming bytes (decoded as UTF-8
with `errors="replace"`).  ANSI passthrough is opt-in via a
`--ansi` flag — by default we strip control sequences so the log
stays grep-friendly.  No PTY, no terminal emulator — Wave 4 is a
viewer, not a replacement for `screen` / `minicom` / `tio`.

The screen's worker thread runs `open_monitor(...)` and pumps
`MonitorEvent`s back via `app.call_from_thread` (the same pattern
Wave 3's `OnboardingScreen` uses).  Ctrl+] dismisses the screen
and surfaces the summary in a notification.

**Alternatives considered:**

- *Embed a real PTY (Textual `Pty` widget)*. Rejected: increases
  scope dramatically; a viewer is enough for 95% of debug
  workflows; users who need `screen` can always shell out.

### D7: MCP `probe_monitor_open` is a session-style tool

Unlike the existing one-shot tools (`build`, `flash`,
`toolchain_apply_install_plan`), `probe_monitor_open` returns a
session id the agent polls:

```python
session = client.call("probe_monitor_open", baud=115200)
# returns {"session_id": "uuid", "started_at": "...", "probe": {...}}

while True:
    chunk = client.call("probe_monitor_poll", session_id=session["session_id"])
    # returns {"new_bytes": "...", "closed": False, "duration_ms": ...}
    if chunk["closed"]:
        break

client.call("probe_monitor_close", session_id=session["session_id"])
```

The session lives in a server-side session table keyed on UUID;
each session owns its own background thread.  The session times
out after 5 minutes of no `poll` activity (auto-close) so a
crashed agent doesn't leak threads forever.

**Alternatives considered:**

- *Stream over MCP transport*. Rejected: MCP is request/response;
  streaming requires SSE or WebSocket support which the current
  MCP SDK doesn't expose generically.
- *Single blocking call returning all bytes*. Rejected: agent
  would have to set a timeout; no incremental visibility.

### D8: Error vocabulary

New error_type strings registered in
`tests/test_errors_uniqueness.py`:

| error_type | When |
|---|---|
| `family-toolchain-probe-not-found` | Lockfile pins probe-rs but the binary isn't in the store (after Wave-2 prune?) |
| `family-toolchain-probe-not-attached` | No probe USB-attached. |
| `family-toolchain-probe-multiple-attached` | More than one probe; `--probe` selector required. |
| `family-toolchain-probe-unauthorised` | Vendor-only probe (proprietary J-Link / locked ST-Link); name the vendor tool. |
| `family-toolchain-erase-aborted` | User answered N / pressed Ctrl+C at the prompt. |
| `family-toolchain-erase-unsupported-region` | `--region <name>` doesn't resolve via the device IR. |
| `family-toolchain-erase-confirmation-required` | MCP agent called `probe_erase` without `confirm=true`. |
| `family-toolchain-erase-probe-failed` | Backend (probe-rs / openocd) returned non-zero during erase. |
| `probe-operation-cancelled` | Ctrl+] in `alloy monitor` (graceful close). |

Every entry has a cookbook anchor in `docs/ERROR_COOKBOOK.md` —
the existing `scripts/check_error_cookbook.py` regression test
verifies one-to-one coverage.

### D9: `alloy reset` is idempotent + safe; no preview tool

Reset is non-destructive (the firmware on the chip stays put).
The orchestrator dispatches it directly without a plan tool —
mirrors Wave 3's `toolchain_status` (read-only) versus
`toolchain_apply_install_plan` (mutating).  The MCP `probe_reset`
tool is correspondingly idempotent: every call returns a
`ResetReport`, no `confirm=true` required.

## Risks / Trade-offs

- **[Risk] Probe detection is platform-specific** — Linux uses
  udev / hidraw, macOS uses IOKit, Windows uses SetupAPI.
  → Mitigation: delegate detection to probe-rs's `list` command;
  parse its JSON output.  Wave 2 already pins probe-rs; we trust
  its detection.  When probe-rs lacks a backend (esp-jtag on
  rare platforms), surface `family-toolchain-probe-not-found`.

- **[Risk] `alloy erase` on the wrong chip bricks the user's
  hardware.**  → Mitigation: D3's two-phase safety gate.  The
  CLI prompt prints the chip id (`This will erase ALL flash on
  STM32G071RB.`) so the user sees what's about to die.  CI gets
  `--auto` but only after `--region` / chip-id validation.

- **[Risk] `alloy monitor`'s baud-rate guess is wrong**, leaving
  the user with garbled UTF-8.  → Mitigation: read the baud from
  `alloy.toml`'s `[uart].debug.baud` config (Wave 1 already
  owns this); `--baud` overrides; default is 115200 only when
  neither resolves.

- **[Risk] RTT mode requires probe-rs ≥ 0.24** — older probe-rs
  pins don't support `probe-rs attach` with RTT.  → Mitigation:
  detect at runtime (probe-rs version output); raise
  `family-toolchain-probe-not-found` with a clear "upgrade
  probe-rs" message when the pinned version is too old.

- **[Risk] MCP monitor sessions leak threads** if the agent
  crashes without calling `probe_monitor_close`.
  → Mitigation: D7's 5-minute idle timeout auto-closes orphaned
  sessions.  A regression test pins the timeout behaviour.

- **[Risk] `--region <name>` aliases differ across devices** —
  one vendor's `bootloader` is another's `boot-rom`.
  → Mitigation: D4 reads from the device IR.  When the IR is
  missing aliases for a device, `--region <name>` raises a
  typed error pointing at the IR file the user can fix.

- **[Risk] Adding three new commands inflates `--help` clutter**.
  → Mitigation: group related verbs in the help output (Wave 4
  rebuilds `cli.py`'s `main` group ordering so reset / erase /
  monitor sit next to flash + debug under a "Hardware" section).

- **[Trade-off] No bidirectional RTT in Wave 4.**  Users who need
  to send bytes back over RTT (test fixtures, command shells)
  must wait for Wave 5.  Acceptable trade-off because Wave 4 is
  already a multi-week ship; bidirectional RTT requires a real
  PTY + send-side serialisation that's out of scope.
