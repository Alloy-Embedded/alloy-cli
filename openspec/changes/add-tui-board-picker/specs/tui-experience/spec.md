## ADDED Requirements

### Requirement: alloy-cli SHALL provide an interactive Board Picker screen

The `BoardPickerScreen` SHALL render a faceted browser of boards
backed by `core.search.boards`.  It SHALL combine free-text search,
filter chips (vendor, ISA, has-feature, tier), a scrollable list,
and a live-updating detail pane.  The screen SHALL be embeddable
inside the onboarding wizard as a modal-style step that returns the
selected `BoardSummary` to its caller.

#### Scenario: Searching narrows the visible list

- **WHEN** the user is on `BoardPickerScreen` with full catalogue
- **AND** the user types `nucleo` into the search field
- **THEN** the visible list SHALL contain only boards matching
  `nucleo` (fuzzy)
- **AND** the count indicator SHALL update (e.g., "showing 4/11")

#### Scenario: Detail pane updates on selection

- **WHEN** the user navigates the list with `↑↓`
- **THEN** the detail pane SHALL re-render with the highlighted
  board's full `BoardManifest` immediately (no perceptible lag)

#### Scenario: Enter returns a selection

- **WHEN** the user presses `Enter` with a board highlighted
- **THEN** the screen SHALL pop, returning the selected
  `BoardSummary` to the caller
- **AND** in the onboarding wizard, the next step SHALL receive
  this value
