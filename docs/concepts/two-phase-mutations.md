# Two-phase mutations

Every destructive operation in alloy-cli follows a **preview →
apply** pattern:

1. **Phase 1** — a read-only tool returns the *plan*: what would
   change, what bytes / regions / files / pins are affected.
2. **Phase 2** — a mutating tool executes the plan, gated behind
   explicit confirmation (`confirm=true` flag, TTY prompt, or
   `--yes` override).

The pattern protects against three classes of bug:

- **Agent hallucination** — an LLM agent asked to "erase the
  bootloader" might pick the wrong region; the plan tool surfaces
  the exact bytes so the user can sanity-check.
- **Typo / misclick** — a developer running `alloy erase` should
  see what they're about to wipe before the wipe lands.
- **Stale context** — a CI script that ran `plan_install` an hour
  ago might dispatch on stale state; the apply step re-resolves.

## Where it shows up

| Surface | Phase 1 | Phase 2 |
|---|---|---|
| MCP peripheral edits | `preview_diff(kind, name, payload)` | `apply_diff(diff_id)` |
| MCP toolchain install | `toolchain_install_plan(family_id)` | `toolchain_apply_install_plan(family_id)` |
| MCP flash erase | `probe_erase_plan(regions=[...])` | `probe_erase(regions=[...], confirm=True)` |
| CLI `alloy erase` | Rich plan table | TTY prompt (default N) or `--auto` / `--yes` |
| TUI Onboarding | Plan-review phase (DataTable) | `[Install]` button + worker thread |

## Implementation contract

The mutating tool **refuses** without explicit confirmation:

```python
# probe_erase without confirm=true → typed envelope
ToolError(
    error_type="family-toolchain-erase-confirmation-required",
    message="probe_erase requires confirm=true; "
            "call probe_erase_plan first.",
)
```

The tool documentation says: "agents MUST call the preview tool
first, surface the plan to the user, get explicit confirmation,
THEN call the apply tool".  Skipping is a contract violation
that surfaces as the typed error.

## TTL on diffs

`preview_diff` returns a `diff_id`; `apply_diff(diff_id)` looks
it up.  Diffs **expire after 5 minutes** so a forgotten preview
doesn't apply against drifted state.  Trying to apply an expired
diff raises `StaleDiffError` — the agent regenerates the preview
and retries.

## CLI ergonomics

For interactive CLI use, the "preview" is a Rich panel rendered
inline + a `click.confirm()` prompt:

```sh
$ alloy erase
┏━━━━━━━━━━━━━━━━━ Erase plan ━━━━━━━━━━━━━━━━━┓
┃ region    base       size                    ┃
┃ all       0x08000000 128.0 KiB               ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
This will erase 128.0 KiB on st/stm32g0/stm32g071rb.  Continue? [y/N]:
```

Default N — pressing Enter without typing aborts.  `--auto` /
`--yes` bypasses the prompt for CI.  `--auto` in non-TTY context
without an explicit `--yes` aborts with a typed message rather
than blocking on STDIN nobody can answer.

## Cross-references

- [`docs/AI_INTEGRATION.md`](../AI_INTEGRATION.md) — the MCP
  surface that exposes preview + apply as separate tools.
- [`docs/RECOVERY.md`](../RECOVERY.md) — `alloy erase`'s safety
  gate.
- [`docs/TOOLCHAIN_ONBOARDING.md`](../TOOLCHAIN_ONBOARDING.md) —
  the toolchain-install variant.
