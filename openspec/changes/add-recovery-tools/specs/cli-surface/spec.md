## ADDED Requirements

### Requirement: alloy-cli SHALL expose ``alloy reset`` for non-destructive target reset

The ``alloy reset`` Click command SHALL issue a CPU or hardware
reset of the connected probe target, dispatching through
``core.probe_orchestrator.reset_target``.  Flags:

- ``--soft`` (default) — software reset via the probe's standard
  reset command.
- ``--hard`` — pulses the nRST line if the probe + target support
  it.
- ``--halt-after-reset`` — leaves the core halted after reset so
  the user can attach a debugger.
- ``--probe <vid:pid:serial>`` — explicit probe selector matching
  ``alloy flash --probe`` semantics.
- ``--project-dir <path>`` — defaults to CWD; used to resolve
  ``.alloy/toolchain.lock`` for the probe-rs / openocd binary.

When no probe is attached the command SHALL exit non-zero with
``family-toolchain-probe-not-attached``.  When more than one is
attached and ``--probe`` is not given, the command SHALL exit
non-zero with ``family-toolchain-probe-multiple-attached`` and
the message SHALL list every detected probe.

After a successful reset the command SHALL print a Rich panel
summarising the probe id, reset method, and elapsed milliseconds.

#### Scenario: alloy reset on a single-attached Nucleo

- **WHEN** the user runs ``alloy reset`` with one ST-Link
  attached and ``--soft`` (default)
- **THEN** the orchestrator SHALL dispatch a soft reset via
  the lockfile-pinned probe-rs
- **AND** the command SHALL exit 0
- **AND** the output SHALL name the probe id + method

#### Scenario: alloy reset with no attached probe

- **WHEN** the user runs ``alloy reset`` with no probe attached
- **THEN** the command SHALL exit non-zero
- **AND** the output SHALL surface
  ``family-toolchain-probe-not-attached``
- **AND** the message SHALL link to
  ``ERROR_COOKBOOK.md#family-toolchain-probe-not-attached``

#### Scenario: alloy reset with multiple attached probes

- **WHEN** the user runs ``alloy reset`` with two probes attached
  and no ``--probe`` selector
- **THEN** the command SHALL exit non-zero
- **AND** the output SHALL list every probe (vid:pid:serial)
- **AND** SHALL surface
  ``family-toolchain-probe-multiple-attached``

### Requirement: alloy-cli SHALL expose ``alloy erase`` with two safety gates

The ``alloy erase`` Click command SHALL erase the chip's flash
through ``core.probe_orchestrator.{plan_erase, execute_erase}``.
Flags:

- ``--region <name|range>`` — partial erase.  Names resolve via
  the device IR's flash bank descriptors.  Ranges use
  ``0xBASE-0xEND`` syntax.  May be repeated to erase several
  regions in one run.
- ``--auto`` / ``--yes`` — suppresses the confirmation prompt.
  Required in non-TTY contexts (CI, subprocess piping); the
  command SHALL refuse to proceed in non-TTY without one of them.
- ``--probe <vid:pid:serial>`` — same selector as ``alloy reset``.
- ``--project-dir <path>``.

In a TTY the command SHALL print the plan (regions + total bytes
+ chip id) and prompt:

```
This will erase <total_bytes> on <chip_id>. Continue? [y/N]
```

Default answer N.  Anything other than ``y`` / ``yes`` (case-
insensitive) SHALL surface
``family-toolchain-erase-aborted`` with exit code 1.  ``--auto``
or ``--yes`` SHALL bypass the prompt.

When ``--region <name>`` does not resolve via the device IR the
command SHALL exit non-zero with
``family-toolchain-erase-unsupported-region`` and the message
SHALL list every region the IR knows about.

#### Scenario: alloy erase in a TTY answered Y

- **WHEN** the user runs ``alloy erase`` with one probe attached
  and answers ``y`` at the prompt
- **THEN** the command SHALL execute the chip-wide erase
- **AND** SHALL exit 0
- **AND** the output SHALL summarise total bytes erased + duration

#### Scenario: alloy erase in a TTY answered N

- **WHEN** the user answers ``n`` at the prompt
- **THEN** no erase SHALL run
- **AND** the command SHALL exit non-zero
- **AND** SHALL surface ``family-toolchain-erase-aborted``

#### Scenario: alloy erase --auto in CI

- **WHEN** the user runs ``alloy erase --auto`` with STDIN closed
- **THEN** no prompt SHALL fire
- **AND** the orchestrator SHALL execute the erase
- **AND** the command SHALL exit 0 on success

#### Scenario: alloy erase without --auto in non-TTY

- **WHEN** the user runs ``alloy erase`` with STDIN closed and no
  ``--auto`` / ``--yes``
- **THEN** the command SHALL exit non-zero
- **AND** SHALL surface ``family-toolchain-erase-aborted`` with
  a message naming the missing flag

#### Scenario: alloy erase --region resolves a named alias

- **WHEN** the user runs ``alloy erase --region bootloader
  --auto`` against a chip whose IR declares a ``bootloader``
  flash region
- **THEN** the orchestrator SHALL plan the erase against the
  resolved region only
- **AND** SHALL execute that subset

#### Scenario: alloy erase --region with an unknown alias

- **WHEN** the user runs ``alloy erase --region not-a-region``
- **THEN** the command SHALL exit non-zero
- **AND** SHALL surface
  ``family-toolchain-erase-unsupported-region``
- **AND** the message SHALL list the region names the IR exposes

### Requirement: alloy-cli SHALL expose ``alloy monitor`` for live UART / RTT viewing

The ``alloy monitor`` Click command SHALL stream bytes from the
target's debug UART (or RTT channel) to stdout.  Flags:

- ``--port <path>`` — explicit serial device; overrides
  autodetect.
- ``--baud <N>`` — explicit baud rate; overrides
  ``alloy.toml [uart].debug.baud``.
- ``--mode raw`` (default) | ``--mode rtt``.
- ``--ansi/--no-ansi`` (default ``--no-ansi``) — pass-through ANSI
  escape sequences when set; strip them otherwise.
- ``--probe <vid:pid:serial>`` — only meaningful in ``rtt``
  mode.
- ``--project-dir <path>``.

When neither ``--port`` nor a project ``[uart].debug`` config
resolves the command SHALL exit non-zero with a clear message.

Pressing ``Ctrl+]`` SHALL raise
``ProbeOperationCancelledError`` from the orchestrator; the
command SHALL catch it and print a one-line summary:

```
Closed monitor session.  <bytes> bytes captured over <duration>.
Last line: "<line>"
```

The exit code SHALL be 0 (graceful disconnect is not a failure).

#### Scenario: alloy monitor inside a project with debug UART configured

- **WHEN** the user runs ``alloy monitor`` inside a project whose
  ``alloy.toml`` declares ``[uart].debug.peripheral``
- **THEN** the command SHALL open the resolved serial device at
  the configured baud
- **AND** stream bytes to stdout

#### Scenario: alloy monitor outside a project with explicit overrides

- **WHEN** the user runs ``alloy monitor --port /dev/cu.usb1234
  --baud 115200`` outside a project
- **THEN** the command SHALL open the explicit port at the
  explicit baud

#### Scenario: alloy monitor Ctrl+] graceful close

- **WHEN** the user presses Ctrl+] mid-session
- **THEN** the command SHALL close the session cleanly
- **AND** print the summary line with byte count + duration
- **AND** exit 0

#### Scenario: alloy monitor with no port and no project config

- **WHEN** the user runs ``alloy monitor`` outside a project
  with no ``--port``
- **THEN** the command SHALL exit non-zero with a clear message
  naming ``--port`` and the project's ``[uart].debug`` field
