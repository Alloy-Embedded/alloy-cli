## ADDED Requirements

### Requirement: the TUI ``DebugScreen`` SHALL gain a Reset / Erase / Open Monitor action group

The Wave-1 placeholder ``DebugScreen`` SHALL be promoted with a
new action group at the top of its layout containing three
buttons:

- ``[Reset]`` — dispatches ``probe_orchestrator.reset_target``
  on a worker thread.  On success the screen flashes a Toast
  with the probe + method.  On failure it surfaces the typed
  envelope as a Toast.
- ``[Erase]`` — opens a modal screen that renders the
  ``probe_orchestrator.plan_erase`` output (regions + total
  bytes).  Buttons in the modal: ``[Confirm]`` (executes via
  ``execute_erase``); ``[Cancel]`` (dismisses).  Mirrors Wave 3's
  ``OnboardingScreen`` plan-review pattern.
- ``[Open Monitor]`` — pushes the new ``MonitorScreen``.

The screen SHALL NOT call ``probe-rs`` / ``openocd`` directly —
all dispatch goes through ``probe_orchestrator``.  Worker threads
follow the Wave-3 pattern: ``run_worker(thread=True)`` +
``app.call_from_thread`` for UI updates.

#### Scenario: Reset button dispatches the orchestrator

- **WHEN** the user presses the ``[Reset]`` button on the
  ``DebugScreen``
- **THEN** the screen SHALL dispatch
  ``probe_orchestrator.reset_target`` on a worker
- **AND** SHALL render a Toast with the probe + method on success

#### Scenario: Erase button opens a confirmation modal

- **WHEN** the user presses the ``[Erase]`` button
- **THEN** a modal SHALL appear with the plan (regions + total
  bytes)
- **AND** SHALL only execute when the user presses
  ``[Confirm]``
- **AND** SHALL dismiss without erasing on ``[Cancel]``

### Requirement: alloy-cli SHALL ship a TUI ``MonitorScreen``

A new ``MonitorScreen`` SHALL render the live monitor session.
Layout:

- Header with the active port + baud + mode + cumulative byte
  count.
- Body: a Textual ``RichLog`` rendering incoming lines.  ANSI
  passthrough opt-in via the screen's ``ansi`` reactive.
- Footer with bindings: ``Ctrl+]`` close, ``Ctrl+L`` clear,
  ``Ctrl+P`` open command palette.

The screen SHALL spawn ``probe_orchestrator.open_monitor`` on a
worker thread and pump ``MonitorEvent``s back via
``app.call_from_thread``.  Closing via Ctrl+] SHALL dismiss with
a typed summary the parent surface can render.

The screen SHALL register via
``register_screen("monitor", title="Monitor", …)`` so the
command palette discovers it.

#### Scenario: opening the screen with a configured project starts the session

- **WHEN** the user opens ``MonitorScreen`` inside a project
  whose ``alloy.toml`` declares the debug UART
- **THEN** the screen SHALL open the resolved port at the
  resolved baud
- **AND** SHALL start streaming incoming bytes into the
  ``RichLog``

#### Scenario: pressing Ctrl+] closes the screen with a summary

- **WHEN** the user presses Ctrl+] mid-session
- **THEN** the screen SHALL dismiss with a typed summary
  (``bytes_captured``, ``duration_ms``, ``last_line``)
- **AND** SHALL stop the worker thread cleanly

#### Scenario: the screen is registered for the command palette

- **WHEN** the user presses Ctrl+P in ``alloy ui``
- **THEN** ``Monitor`` SHALL appear as a discoverable entry
- **AND** selecting it SHALL push ``MonitorScreen`` onto the stack
