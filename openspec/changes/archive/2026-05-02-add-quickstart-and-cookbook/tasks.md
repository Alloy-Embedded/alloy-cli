# Tasks — add-quickstart-and-cookbook

## Phase 1: Quickstart

- [x] 1.1 `docs/QUICKSTART.md` walkthrough: install →
      `alloy new` → `alloy build` → `alloy flash` →
      verify on a real Nucleo-G071RB.
- [x] 1.2 The doc references the existing screenshots in
      `docs/images/` (no new SVGs minted; the snapshot
      harness keeps them in sync).
- [x] 1.3 README hero badge link lands in a follow-up
      doc-only PR — the spec already pins the contract.

## Phase 2: Progressive examples

- [x] 2.1 `docs/EXAMPLES/01-blinky/`: GPIO + Board::init.
- [x] 2.2 `docs/EXAMPLES/02-uart-echo/`: typed UART add.
- [x] 2.3 `docs/EXAMPLES/03-spi-flash/`: SPI driver against
      a synthetic AT25 part with software CS.
- [x] 2.4 `docs/EXAMPLES/04-dma-double-buffer/`: UART RX +
      `suggest_dma_pair` auto-allocation (with explicit
      channels for reproducibility).
- [x] 2.5 Each example has a `README.md` walking through
      the diff against the previous step plus a
      schema-valid `alloy.toml`.

## Phase 3: Error cookbook

- [x] 3.1 `docs/ERROR_COOKBOOK.md` — one section per
      `AlloyCliError.error_type` plus the MCP `ToolError`
      types (`tool-not-found`, `diff-not-found`).
- [x] 3.2 Each section: trigger / message / fix / related
      MCP tool.
- [x] 3.3 `scripts/check_error_cookbook.py` walks the
      Python tree, harvests every `error_type = "..."`
      assignment, and asserts the cookbook has a matching
      `## <error-type>` heading.

## Phase 4: Cheatsheet + scaffold helper

- [x] 4.1 `scripts/generate_cheatsheet.py` walks the live
      Click tree and writes
      `docs/CHEATSHEET.md`.  `--check` mode exits non-zero
      on drift; CI calls that mode.
- [x] 4.2 `alloy new --from-example <name>` scaffolds from
      a `docs/EXAMPLES/` entry; mutually exclusive with
      `--board` / `--device`; renames the example's
      `[project].name` to the new project's name.

## Phase 5: Tests

- [x] 5.1 `tests/test_quickstart_and_cookbook.py` (17
      cases) covers: quickstart references the right
      commands, every example parses, `--from-example`
      help / clash / unknown-name / round-trip, cheatsheet
      `--check` succeeds + spot-check covers `alloy add
      uart` / `alloy build` / `alloy boards` / `alloy
      doctor`, error cookbook check passes + spot-check
      anchors.
- [x] 5.2 The `alloy new --from-example` round-trip seeds a
      stub board catalogue from
      `tests/snapshots/_render` and asserts the resulting
      `alloy.toml` is renamed AND retains the example's
      peripherals.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/developer-experience/spec.md`
      (new capability).
- [x] 6.2 `openspec validate add-quickstart-and-cookbook
      --strict` passes.
