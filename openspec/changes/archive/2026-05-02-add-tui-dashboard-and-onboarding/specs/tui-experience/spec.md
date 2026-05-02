## ADDED Requirements

### Requirement: alloy-cli SHALL provide a project Dashboard screen

The Dashboard SHALL be the default landing screen when `alloy` is
run inside a configured project (or `alloy ui` is invoked).  It
SHALL surface the chosen board / device, toolchain + probe status,
clock profile, peripherals list, last build summary, memory usage
mini-bar, and a recent-activity log.  It SHALL expose hotkeys for
build / flash / debug / add / clocks / memory.

#### Scenario: Dashboard renders all panels for a fully-configured project

- **WHEN** the user runs `alloy` (no args) inside a project with
  4 peripherals, a successful last build, and 3 events in the
  activity log
- **THEN** the Dashboard SHALL render with all five panels
  (peripherals, build, memory, activity, top status)
- **AND** every keybinding from the hotkey row SHALL be functional
- **AND** the snapshot SHALL match the golden file

#### Scenario: Dashboard handles empty project gracefully

- **WHEN** the user runs `alloy ui` inside a project with zero
  peripherals and no prior build
- **THEN** the peripherals panel SHALL show "No peripherals yet.
  Press 'a' to add one."
- **AND** the build panel SHALL show "Never built.  Press 'b'."

### Requirement: alloy-cli SHALL provide an onboarding wizard for new users

The Onboarding wizard SHALL guide a new user from "no project" to
"buildable project" in at most six steps: name → board → clock
profile → starter peripheral (optional) → diff confirmation →
build (optional).  Every step SHALL be skippable; partial state
SHALL be persistable to a `.alloy/onboarding.json` so the user
can resume.

#### Scenario: Onboarding wizard completes without skipping

- **WHEN** the user runs `alloy new` with no flags in an empty
  directory
- **AND** completes all six steps
- **THEN** a project tree SHALL be created with the chosen board,
  clock profile, and one peripheral
- **AND** the Dashboard SHALL open automatically afterwards
