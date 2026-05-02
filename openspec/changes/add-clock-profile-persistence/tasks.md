# Tasks — add-clock-profile-persistence

## Phase 1: Schema + dataclasses

- [ ] 1.1 Schema bump: `alloy.toml [clocks].profiles` map
      lands under `schema/alloy_toml_v1_1.json` (additive).
- [ ] 1.2 `core.clocks.ClockProfileBody` frozen dataclass
      (`source`, `pll_n`, `pll_r`, `sysclk_hz`, `hclk_div`,
      `apb1_div`, `apb2_div`, plus an open `extras: dict`).

## Phase 2: Core operations

- [ ] 2.1 `core.clocks.profile_from_rates(rates) -> ClockProfileBody`.
- [ ] 2.2 `core.clocks.save_profile(config, name, body) ->
      UnifiedDiff` — emits the alloy.toml diff.
- [ ] 2.3 `core.clocks.activate_profile(config, name) ->
      UnifiedDiff`; raises `UnknownProfileError` when the name
      is absent.
- [ ] 2.4 Round-trip tests: deterministic emission, schema
      validation negative cases.

## Phase 3: TUI wiring

- [ ] 3.1 `ClockTreeScreen.action_save_profile` opens a name
      input + DiffModal preview.
- [ ] 3.2 `p` cycles between named profiles + `(custom)` for
      unsaved live edits.
- [ ] 3.3 Validation: reject empty / duplicate names with a
      diagnostic.

## Phase 4: MCP tools

- [ ] 4.1 `alloy.save_clock_profile(name, rates)` MCP tool.
- [ ] 4.2 `alloy.activate_clock_profile(name)` MCP tool — wraps
      the existing `set_clock_profile` semantics with the new
      activate operation.

## Phase 5: Tests

- [ ] 5.1 Pure-function tests for save / activate / from_rates.
- [ ] 5.2 Pilot-driven test: ClockTreeScreen → override PLL →
      Ctrl+S → DiffModal apply → file diff lands.
- [ ] 5.3 MCP integration test: save then activate via the
      registry; the resulting alloy.toml has the profile pinned.

## Phase 6: Spec + final checks

- [ ] 6.1 Spec deltas in `specs/project-format/spec.md` and
      `specs/tui-experience/spec.md`.
- [ ] 6.2 `openspec validate add-clock-profile-persistence
      --strict` passes.
- [ ] 6.3 `docs/PROJECT_FORMAT.md` table extended with the new
      `[clocks].profiles` block.
