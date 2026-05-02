# Promote `alloy debug` From Wrapper to TUI Front-End

## Why

`alloy debug` today spawns `probe-rs gdb-server` and the user's
configured GDB front-end (typically `arm-none-eabi-gdb -tui`).
That works but undersells the product: every other developer
surface in alloy-cli is a first-class Textual screen, and the
debug experience drops to "hope your GDB knows what it's
doing."

REVIEW.md item 19 calls this out explicitly: *"alloy debug is a
thin wrapper.  No GDB UI; we just spawn the user's configured
one.  Wiring a Textual GDB front-end alongside the existing
screens is a future polish iteration."*

This proposal lands that polish — a `DebugScreen` with the
five panels every embedded debugger needs, driven by an MI2
session against `probe-rs gdb-server`.

## What Changes

### `core.gdb` adapter

- New `core.gdb.GdbSession(runner: CommandRunner, port: int)`
  manages a `arm-none-eabi-gdb -i=mi2` subprocess.
- Typed methods: `connect_target()`, `load(elf_path)`,
  `set_breakpoint(loc)`, `delete_breakpoint(id)`,
  `continue_()`, `step()`, `next()`, `finish()`, `interrupt()`,
  `eval(expr)`, `read_memory(addr, n)`, `disassemble(start,
  end)`.
- All methods return typed dataclasses parsed from MI2
  output (`StopReason`, `Frame`, `Variable`, `Register`,
  `MemorySlice`).  Tests mock the wire-level MI2 stream via
  `FakeRunner`.

### `tui.screens.DebugScreen`

- Five panels in a 2×3 grid (3rd column gets the bottom
  row):
  - **Source** — current file with line markers,
    breakpoints in gutter, PC arrow.  Backed by `Syntax`
    rendering of the source on disk.
  - **Call stack** — `DataTable` of frames, `Enter` jumps
    Source.
  - **Locals + watches** — `Tree` widget grouping locals
    and user-added watches.
  - **Registers** — `DataTable` (general / FPU / system
    register columns).
  - **GDB log** — scrollable `RichLog` of every MI2
    command + response (debugging the debugger).
- Bindings: `c` continue, `s` step in, `n` step over,
  `o` step out, `b` toggle breakpoint, `i` interrupt,
  `w` add watch, `Esc` close + tear down session.

### CLI integration

- `alloy debug --tui` (default true on a TTY) launches the
  screen.  `--no-tui` keeps the wrapper-only behaviour
  for terminals that can't run Textual.
- Probe selection / target chip are inferred from
  `alloy.toml` plus `core.flash.detect_probes` (already
  there).
- `alloy debug --port N` overrides the gdb-server port for
  parallel sessions.

### Crash recovery

- If the `probe-rs gdb-server` subprocess exits, the screen
  surfaces a `notify(severity="error")` and tears the
  session down without leaving an orphan PID.

## Impact

- The debug experience matches CubeMX / VS Code in terms of
  what a user can see at a glance, but stays in-terminal.
- Embedded developers gain a unified workflow: `alloy build`
  → `alloy flash` → `alloy debug` all in the same Textual
  shell.
- The `core.gdb` adapter becomes a reusable seam — future
  proposals can mount it from MCP (`alloy.gdb_step`,
  `alloy.gdb_eval`) for AI-assisted debugging.

## What this DOES NOT do

- Does not implement reverse / record-replay debugging.
- Does not embed an HTTP/WebSocket bridge to remote
  debuggers; the gdb-server stays local.
- Does not introduce a graphical disassembly view; the
  panel uses the same `Syntax` widget Source uses.
- Does not bundle GDB or probe-rs — the existing toolchain
  detection (Doctor) covers that.
