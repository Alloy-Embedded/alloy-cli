# Add Real Upgraders Behind `alloy update`

## Why

`alloy update` today resolves pending upgrades, prints them, and —
on `--apply` — rewrites `.alloy/version.lock` with the new pinned
versions.  **No actual pip install / git submodule / SDK download
happens.**  The contract is right; the upgraders are stubs.

Users who run `alloy update` and then `alloy build` against a
"new" pinned version get the same binaries as before, because the
underlying packages weren't actually updated.  That's a subtle
correctness bug: the lockfile says we're on alloy 0.7.5 but
`pip show alloy` still reports 0.7.3.

## What Changes

### Per-component upgraders

`core.update.UPGRADERS` becomes a registry of typed callables:

```
ComponentUpgrader = Callable[[Upgrade, UpgradeContext], UpgradeOutcome]

UPGRADERS = {
    "alloy":             pip_upgrader("alloy"),
    "alloy-codegen":     pip_upgrader("alloy-codegen"),
    "alloy-cli":         pip_upgrader_with_restart("alloy-cli"),
    "alloy-devices-yml": git_submodule_upgrader,
}
```

- `pip_upgrader(name)` — invokes
  `python -m pip install --upgrade <name>==<target>` via the
  shared `core.process.runner`; captures stdout/stderr; returns
  an `UpgradeOutcome`.
- `pip_upgrader_with_restart("alloy-cli")` — same, plus a
  user-facing notice asking the user to re-launch (we can't
  swap `sys.executable` mid-process).
- `git_submodule_upgrader` — runs
  `git -C data/devices fetch && git -C data/devices checkout <sha>`
  with the target version mapped through alloy-devices-yml's
  release tags.

### Atomic application

- `core.update.apply_upgrades` runs every upgrader in dependency
  order: **alloy-devices-yml → alloy-codegen → alloy → alloy-cli**.
- If any step fails, **the lockfile is not rewritten**.  Any
  partial pip changes get noted in the failure summary so the
  user knows what to roll back.
- `--dry-run` already exists; no changes there.

### Subprocess seam

- Every call goes through `core.process.runner` — same FakeRunner
  that powers the build/flash tests covers update too.

### CI guardrails

- A new GitHub Actions matrix entry `update-smoke.yml` runs
  `alloy update --dry-run` against the repo's lockfile on every
  PR; failures land in the PR check.

## Impact

After this lands, **the lockfile and the installed packages stay
in sync**.  Users can trust `alloy update` end-to-end.

The existing dry-run / frozen / atomic contracts are unchanged;
this is a fill-in for the no-op upgrader stubs.

## What this DOES NOT do

- Does not introduce a per-package version-resolution algorithm
  (PyPI's resolver does the work).
- Does not implement rollback of a partially-applied pip install
  (pip handles its own atomicity per-package).
- Does not introduce an SDK download manager — alloy itself ships
  via PyPI today.  The placeholder for "alloy" can be revisited
  when the SDK split lands in a separate proposal.
- Does not change the `alloy update --frozen` semantics.
