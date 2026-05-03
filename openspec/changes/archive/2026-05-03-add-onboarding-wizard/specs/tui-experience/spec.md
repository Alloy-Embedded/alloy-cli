## ADDED Requirements

### Requirement: the TUI ``OnboardingScreen`` SHALL implement a real install wizard

The Wave-1 placeholder ``OnboardingScreen`` SHALL be promoted to a
fully-functional install wizard.  It SHALL render three lifecycle
phases:

1. **Family picker** — when the project has no ``alloy.toml`` (or
   the resolved family is unknown), present a sortable list of
   curated boards from ``alloy_cli.core.boards.load_catalog()``;
   selecting one resolves the family.  When the project already
   resolves a family, this phase auto-completes.
2. **Plan review** — render every required + recommended tool the
   family declares as a Rich/Textual ``DataTable`` with columns
   ``tool``, ``version``, ``source``, ``status``, ``size``.  Vendor
   tools render as a dim row with their install_doc URL.  The user
   can proceed via ``[Install]`` or back out via ``[Cancel]``.
3. **Live progress** — once Install is pressed, dispatch
   ``toolchain_orchestrator.install_family`` on a worker thread.
   The screen subscribes to the ``InstallEvent`` stream and updates
   one ``InstallProgressWidget`` row per tool: ``ToolStarted`` →
   spinner; ``ToolDownloaded`` → progress bar; ``ToolInstalled`` →
   green check; ``ToolFailed`` → red X with the typed
   ``error_type``; ``ToolSkippedVendor`` → dim row with the URL.
4. **Completion** — when every event has fired, render a final
   ``DoneScreen`` panel with concrete next-step commands and an
   ``[Exit wizard]`` button.

The screen SHALL be reusable: ``alloy new`` interactive mode opens
it after scaffolding, ``alloy ui`` exposes it via the command
palette, and ``alloy setup`` enters it when ``--no-tui`` is not
specified.  Cancelling at any phase SHALL raise
``OnboardingCancelledError`` from the spawning context, which the
CLI maps to exit code 130 (SIGINT convention).

The screen SHALL NOT call ``toolchain_manager.install`` or
``tool_sources.adapter_for`` directly.  All install logic flows
through ``toolchain_orchestrator.install_family``; the screen only
renders events and dispatches user actions.

#### Scenario: opening the wizard inside a stm32g0 project skips the family picker

- **WHEN** the user opens ``OnboardingScreen`` inside a project
  whose alloy.toml resolves to stm32g0
- **THEN** the family picker phase SHALL auto-complete
- **AND** the plan-review phase SHALL render with stm32g0's
  required + recommended tools
- **AND** the active host's pinned URL + size SHALL appear per row

#### Scenario: clicking Install drives the orchestrator and updates progress live

- **WHEN** the user clicks ``[Install]`` after the plan renders
- **THEN** a worker thread SHALL spawn
  ``toolchain_orchestrator.install_family``
- **AND** the screen's ``InstallProgressWidget`` rows SHALL
  update from ``ToolStarted → ToolDownloaded → ToolInstalled``
  in real time as events fire
- **AND** the final phase SHALL render the "All set" panel with
  ``alloy build`` / ``alloy flash`` next-step commands

#### Scenario: vendor tool renders dim with install_doc URL

- **WHEN** the wizard runs against a family whose recommended
  list contains a vendor tool
- **THEN** the plan-review row for that tool SHALL render dim
- **AND** the install_doc URL SHALL be visible inline (or behind
  a hover hint)
- **AND** during the live phase, the row SHALL emit
  ``ToolSkippedVendor`` immediately and stay dim — no progress
  bar, no spinner

#### Scenario: cancelling mid-install raises the typed error

- **WHEN** the user clicks ``[Cancel]`` after one tool has
  already installed but two more are pending
- **THEN** the wizard SHALL surface
  ``OnboardingCancelledError`` to the calling context
- **AND** the partial outcomes SHALL be attached to the
  exception
- **AND** the spawning ``alloy setup`` / ``alloy new`` SHALL
  exit with code 130
- **AND** the toolchain store SHALL preserve the one tool that
  did install (Wave-2 atomicity)

#### Scenario: the screen is registered in the screen registry

- **WHEN** a contributor opens ``alloy ui`` and presses
  ``Ctrl+P`` for the command palette
- **THEN** ``Onboarding`` SHALL appear as a discoverable entry
- **AND** selecting it SHALL push the wizard onto the screen
  stack
