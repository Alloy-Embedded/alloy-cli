# Tasks — add-cli-boards-and-devices

## Phase 1: Search core

- [ ] 1.1 `core.search.boards.search(query, filters) ->
      tuple[BoardSummary, ...]` — fuzzy match against board_id /
      mcu / vendor / family.
- [ ] 1.2 `core.search.devices.search(query, filters,
      include_bulk) -> tuple[DeviceSummary, ...]` — same shape.
- [ ] 1.3 Filter facets: vendor, ISA / core, has-feature
      (USB / ETH / BLE / CAN / WiFi), tier.
- [ ] 1.4 Has-feature derivation from IR (e.g., "USB" present iff
      device has a `usb_controllers[]` entry).

## Phase 2: CLI commands

- [ ] 2.1 `cli.boards` Click command with all flags + positional
      detail mode.
- [ ] 2.2 `cli.devices` Click command with same flags + `--all` /
      `--admitted` toggle.
- [ ] 2.3 `--json` output mode for scripting (stable schema; goes
      into `specs/cli-surface/spec.md`).

## Phase 3: Output formatting

- [ ] 3.1 Rich-formatted human output: table with columns chosen
      per filter (e.g., when filtering by vendor, hide vendor
      column).
- [ ] 3.2 `alloy boards <id>` detail card: board manifest +
      cross-reference to device IR identity + clock profiles.
- [ ] 3.3 Pagination / clipping for very large results — show
      `[N more · use --json or `alloy boards | less`]`.

## Phase 4: Tests

- [ ] 4.1 Unit tests for `core.search.boards` against fixture
      catalogue.
- [ ] 4.2 Unit tests for `core.search.devices` against the
      submodule.
- [ ] 4.3 Integration test: `alloy boards --search nucleo --json |
      jq` returns at least one entry.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/cli-surface/spec.md` — including
      the JSON output schema.
- [ ] 5.2 `openspec validate add-cli-boards-and-devices --strict`
      passes.
