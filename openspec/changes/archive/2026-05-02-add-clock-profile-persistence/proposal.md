# Persist Clock Profile Edits to alloy.toml

## Why

`ClockTreeScreen` lets users override individual nodes (HSI/PLL/
SYSCLK rates) and immediately propagates the change through the
in-memory rate map.  But `Ctrl+S` is a stub notification — the
overrides never reach `alloy.toml`.

That blocks two real workflows:

1. **Custom clock profiles**.  A user dials in a 96 MHz HSI-driven
   profile, saves it as `dev_low_power`, and expects every later
   `alloy build` to inherit it.
2. **AI-driven clock tuning**.  The MCP server has
   `set_clock_profile(profile)` but the only thing it can change
   today is `[clocks].profile`; there's no way to *create* a new
   profile from explicit rates.

Both unblock once `[clocks]` grows a `profiles` map.

## What Changes

### Schema bump (in tandem with `enrich-peripheral-kinds`)

- `alloy.toml [clocks]` already accepts an open `profile: str`.
  We extend it with an optional `profiles: dict[name → profile
  body]`.  Profile body shape:
  ```toml
  [clocks.profiles.dev_low_power]
  source       = "HSI"
  pll_n        = 24
  pll_r        = 2
  sysclk_hz    = 96_000_000
  hclk_div     = 1
  apb1_div     = 2
  apb2_div     = 1
  ```
- Schema-version bump piggy-backs on
  `enrich-peripheral-kinds` (1.0 → 1.1).  Files that don't
  declare `[clocks.profiles]` keep working.

### Core operations

- `core.clocks.save_profile(config, name, body) -> UnifiedDiff`
  emits the diff that adds / updates the named profile.
- `core.clocks.activate_profile(config, name) -> UnifiedDiff`
  switches `[clocks].profile` to the named entry; raises
  `UnknownProfileError` when it's missing.
- `core.clocks.profile_from_rates(rates: Mapping[str, int]) ->
  ClockProfileBody` derives a profile body from the in-screen
  override map.

### TUI wiring

- `ClockTreeScreen.action_save_profile` opens a small modal:
  - Prompts for a profile name (default
    `custom_<timestamp>`).
  - Presents the diff via `DiffModal` (existing widget).
  - Applies via `core.clocks.save_profile`.
- `p` cycles between every named profile + `(custom)` for live
  edits not yet saved.

### MCP

- `alloy.save_clock_profile(name, rates)` and
  `alloy.activate_clock_profile(name)` MCP tools delegate to the
  new core ops.

## Impact

Closes the "I can change clocks but they don't stick" gap from
`docs/REVIEW.md`.  AI agents can now author + activate full
clock profiles through MCP, not just toggle which one is
selected.

## What this DOES NOT do

- Does not implement the full PLL M/N/R algebra — that lives in
  alloy-codegen and lands together with the codegen integration
  proposal.  Today the profile body is a flat map of named rates
  + dividers; the codegen consumer translates that into vendor
  CMSIS `RCC_*` calls.
- Does not introduce profile inheritance or composition.
- Does not add a CLI subcommand for clock profile editing — the
  TUI + MCP cover the spec scenarios.
