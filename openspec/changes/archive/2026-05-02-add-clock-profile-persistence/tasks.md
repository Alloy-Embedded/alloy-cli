# Tasks — add-clock-profile-persistence

## Phase 1: Schema + dataclasses

- [x] 1.1 Schema bump: `alloy.toml [clocks].profiles` map
      lands under `schema/alloy_toml_v1_1.json` (additive,
      `patternProperties` validates names + body shape).
- [x] 1.2 `core.clocks.ClockProfileBody` frozen dataclass
      (`source`, `pll_n`, `pll_r`, `sysclk_hz`, `hclk_div`,
      `apb1_div`, `apb2_div`, plus an open `extras: dict`).

## Phase 2: Core operations

- [x] 2.1 `core.clocks.profile_from_rates(rates) -> ClockProfileBody`
      (heuristic source: HSE → PLL → HSI fallback).
- [x] 2.2 `core.clocks.save_profile(config, name, body) ->
      UnifiedDiff` — emits the alloy.toml diff via the shared
      `_emit_toml` so it round-trips byte-stable.
- [x] 2.3 `core.clocks.activate_profile(config, name) ->
      UnifiedDiff`; raises `UnknownProfileError` when the name
      is absent from `[clocks].profiles`.
- [x] 2.4 Round-trip tests: deterministic emission as
      `[clocks.profiles.<name>]` sub-tables, `_check_clock_
      profile_reference` rejects orphan `[clocks].profile`
      pointers, missing `source` triggers schema validation.

## Phase 3: TUI wiring

- [x] 3.1 `ClockTreeScreen.action_save_profile` opens a name
      input modal (`_ProfileNameModal`) + `DiffModal` preview;
      apply writes the diff and refreshes the in-screen profile
      rotation so `p` immediately reflects the new entry.
- [x] 3.2 `p` cycles between named profiles + `(custom)` for
      unsaved live edits (rotation always ends with `_CUSTOM_LABEL`).
- [x] 3.3 Validation: `_ProfileNameModal._submit` rejects empty
      / duplicate / syntactically-invalid names with an inline
      diagnostic banner before dismissing.

## Phase 4: MCP tools

- [x] 4.1 `alloy.save_clock_profile(name, rates)` MCP tool —
      delegates to `core.clocks.save_profile` and caches the
      diff under a `diff_id`.
- [x] 4.2 `alloy.activate_clock_profile(name)` MCP tool —
      strict counterpart of the lenient legacy
      `set_clock_profile`; raises `unknown-clock-profile`
      `ToolError` on missing names.

## Phase 5: Tests

- [x] 5.1 Pure-function tests for `save_profile` /
      `activate_profile` / `profile_from_rates` (10 cases).
- [x] 5.2 Pilot-driven test: ClockTreeScreen → override PLL →
      save flow → DiffModal apply → file gains
      `[clocks.profiles.dev_low_power]` block.  `p` cycles
      every named profile + `(custom)`.  Name-modal rejects
      empty, duplicate, and invalid-character inputs.
- [x] 5.3 MCP integration test: `save_clock_profile` →
      `apply_diff` → `activate_clock_profile` → `apply_diff`
      end-to-end; the resulting alloy.toml has the profile
      pinned.  Unknown-name and invalid-name paths return
      structured `ToolError`s.

## Phase 6: Spec + final checks

- [x] 6.1 Spec deltas in `specs/project-format/spec.md` and
      `specs/tui-experience/spec.md`.
- [x] 6.2 `openspec validate add-clock-profile-persistence
      --strict` passes.
- [x] 6.3 `docs/PROJECT_FORMAT.md` table extension lands in a
      follow-up doc-only PR — the spec already pins the
      contract.
