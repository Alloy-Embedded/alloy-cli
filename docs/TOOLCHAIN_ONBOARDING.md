# Toolchain onboarding

Wave 3 of the toolchain-management track welds the building blocks
from Waves 1–2 into the user-facing flows so a new contributor goes
from `pip install alloy-cli` to a flashed board without ever
leaving alloy-cli.  This doc is the reference for those flows.

Cross-links:

- [TOOLCHAIN_REGISTRY.md](TOOLCHAIN_REGISTRY.md) — Wave 1: the
  per-MCU-family manifest format + extends chains.
- [TOOLCHAIN_INSTALLER.md](TOOLCHAIN_INSTALLER.md) — Wave 2: pin
  files, content-addressed store, lockfile, source adapters.
- [QUICKSTART.md](QUICKSTART.md) — five-minute walkthrough that
  uses these flows.
- [ERROR_COOKBOOK.md](ERROR_COOKBOOK.md) — every typed error_type
  the orchestrator can surface.

---

## The four entry points (and the MCP write-side)

There are five surfaces that all dispatch through the **same**
shared orchestrator (`alloy_cli.core.toolchain_orchestrator.
install_family`).  Pick the one that matches the situation:

| Situation | Reach for |
|---|---|
| "I'm scaffolding a brand-new project." | `alloy new --board <id>` (post-scaffold prompt) |
| "I cloned an existing project; toolchain is missing." | `alloy doctor --fix` |
| "I have nothing — I'm completely new." | `alloy setup` |
| "I'm in the TUI dashboard and want to install or repair." | The `Onboarding` screen (Ctrl+P → "Onboarding") |
| "I'm an LLM agent on the MCP transport." | `alloy.toolchain_install_plan` → `alloy.toolchain_apply_install_plan` (two-phase) |

All five route through `install_family` — one source of truth for
the tier walk, vendor short-circuit, lockfile update, and host
detection.  Each entry point owns ONLY its UI shell.

### `alloy new --install-toolchain`

After `alloy new` writes the project tree, it offers to install
the family's toolchain right then:

```sh
alloy new firmware --board nucleo_g071rb     # default Y in a TTY
```

Flag tri-state (matches design D3):

- `--install-toolchain` — install regardless of TTY.
- `--no-install-toolchain` — skip regardless of TTY.
- (default) — Y in a TTY, N otherwise (so CI never blocks on a
  prompt).

`--auto` skips the confirmation prompt; combine with
`--install-toolchain` for fully non-interactive installs.

### `alloy doctor --fix`

`--fix` extends the existing auto-fixer queue (submodule init, MCP
pip install) with a synthetic `toolchain:<tool>` row for every
missing required non-vendor tool the family declares:

```sh
alloy doctor --fix
alloy doctor --fix --with-recommended    # also installs recommended tier
```

Vendor tools (STM32CubeProgrammer, nrfjprog, J-Link) stay
info-severity with the install_doc URL — never auto-fetched.

### `alloy setup`

The friendliest entry point — guided wizard for "I'm new":

```sh
alloy setup --board nucleo_g071rb --auto    # outside a project
alloy setup --auto                          # inside a project
alloy setup --no-tui                        # force the line wizard
```

Detects the project state (alloy.toml? family resolves?) and
either embeds the `alloy new` flow first or skips straight to the
install plan.

### TUI `OnboardingScreen`

Three-phase wizard reachable from `alloy ui` (Ctrl+P → Onboarding):

1. **Family picker** — auto-completes when the project resolves a
   family; otherwise renders a tier-sorted board list.
2. **Plan review** — DataTable of every tool the family declares.
   Vendor rows render dim with the install_doc URL inline.
3. **Live progress** — worker thread runs `install_family`, events
   stream back via `app.call_from_thread`.

Cancellation mid-install raises `OnboardingCancelledError` with the
partial outcomes attached.  The spawning CLI maps it to exit 130.

### MCP `alloy.toolchain_apply_install_plan`

The mutating write-side of Wave 2's read-only
`toolchain_install_plan`.  LLM agents follow the **two-phase**
pattern:

1. `alloy.toolchain_install_plan(family_id="stm32g0")` — preview
   download set + sizes; surface to the user; ask for explicit
   confirmation.
2. `alloy.toolchain_apply_install_plan(family_id="stm32g0")` —
   actually execute the install.

Worked example (pseudocode):

```python
plan = client.call("toolchain_install_plan", family_id="stm32g0")
# Surface plan["plan"], plan["skipped_vendor"], plan["total_size_bytes"]
# to the user; get confirmation.
report = client.call("toolchain_apply_install_plan", family_id="stm32g0")
for row in report["outcomes"]:
    print(row["tool"], row["state"], row["reason"])
```

Idempotent: a re-run on a fully-installed family returns every row
with `skipped=true, reason="already-installed"` and
`total_bytes_downloaded=0`.

---

## The shared orchestrator API

All five surfaces dispatch through one function:

```python
from alloy_cli.core.toolchain_orchestrator import install_family

report = install_family(
    manifest,                       # FamilyManifest from toolchain_registry
    *,
    project_root=None,              # when set, .alloy/toolchain.lock updates
    include_optional=False,         # extend the walk to the optional tier
    force=False,                    # re-install even when SHA matches
    on_event=None,                  # Callable[[InstallEvent], None]
    downloader=None,                # Downloader Protocol — tests pass FakeDownloader
)
```

Returns a frozen `InstallReport` with one `InstallOutcome` per tool
the walker visited (in tier order: required → recommended →
optional when included).

### `InstallEvent` (sealed union)

The `on_event` callback receives one of:

- `ToolStarted(tool, version, source, url, size_bytes)` — adapter
  resolved an artefact; install is about to begin.
- `ToolDownloaded(tool, version, bytes_downloaded)` — bytes
  finalised + SHA verified; extraction next.
- `ToolInstalled(tool, version, sha256, store_path,
  bytes_downloaded, udev_rules_path, skipped)` — atomic promotion
  done; lockfile pin staged.  `skipped=True` means the manager
  treated this as a no-op (already installed at the same SHA).
- `ToolFailed(tool, version, error_type, message)` — typed install
  error; the walker continues with the next tool.
- `ToolSkippedVendor(tool, version, install_doc_url)` — vendor
  (EULA-gated) tool; never spawns a download.
- `ToolSkippedHostUnsupported(tool, version, host,
  supported_hosts)` — active host has no pin for this tool.

### `InstallOutcome`

One row per visited tool.  `state` is one of:

- `installed` — newly downloaded + extracted.
- `skipped-already-installed` — present in the store at the same SHA.
- `skipped-vendor` — vendor short-circuit fired.
- `skipped-host-unsupported` — no pin for the active host.
- `failed` — install error; `error_type` + `error_message` carry
  the diagnostic.

### `InstallReport`

The aggregate the walker returns:

- `outcomes: tuple[InstallOutcome, ...]`
- `installed_count: int` — count of `installed` + `already-installed`.
- `failed_count: int`
- `vendor_skipped: tuple[InstallOutcome, ...]`
- `total_bytes_downloaded: int`
- `lockfile_updated: bool`
- `lockfile_path: Path | None`
- `family_id: str`
- `host: HostTriple`

---

## Vendor-tool contract

Vendor (EULA-gated) tools — STM32CubeProgrammer, nrfjprog,
J-Link, et al. — are NEVER auto-installed.  Every surface honours
this:

- `alloy new` post-scaffold prompt: vendor row in the plan table is
  styled as `skip` with the install_doc URL.
- `alloy doctor --fix`: vendor row stays info-severity, never
  queued for auto-install.
- `alloy setup`: same plan rendering as `alloy new`.
- TUI `OnboardingScreen`: vendor row renders dim with the URL
  inline; never gets a spinner / progress bar.
- MCP `apply_install_plan`: outcome carries `skipped=true,
  reason="vendor", install_doc_url="https://…"`.

The install_doc URL is per-OS — derived from the family manifest's
`install_docs` map keyed on `macos` / `linux` / `windows`.

---

## Cancellation contract

SIGINT mid-install or an explicit cancel button raises
`OnboardingCancelledError` (`error_type="onboarding-cancelled"`)
with `partial_outcomes` carrying the tools that already finished
before the abort.

The CLI surfaces map this to **exit code 130** (SIGINT
convention).  See [ERROR_COOKBOOK.md#onboarding-cancelled](
ERROR_COOKBOOK.md#onboarding-cancelled) for the recovery checklist.

The MCP apply tool does NOT propagate `OnboardingCancelledError`
(MCP transport has no SIGINT semantics) — agents see the typed
envelope on a tool-level cancel only.

---

## Where the code lives

- `src/alloy_cli/core/toolchain_orchestrator.py` — the shared
  walker (UI-free).
- `src/alloy_cli/commands/_install_view.py` — Rich rendering of
  plans + reports + event log lines.
- `src/alloy_cli/commands/new.py` — `alloy new` post-scaffold prompt.
- `src/alloy_cli/commands/doctor.py` — `alloy doctor --fix`
  toolchain auto-installer dispatch.
- `src/alloy_cli/commands/setup.py` — `alloy setup` standalone
  wizard.
- `src/alloy_cli/tui/screens/onboarding.py` — TUI 3-phase wizard.
- `src/alloy_cli/mcp/tools.py::_tool_toolchain_apply_install_plan`
  — MCP write-side tool.

A regression test (`tests/test_toolchain_onboarding_contract.py`)
enforces "every entry point dispatches through `install_family`":
any new file under `commands/`, `tui/`, or `mcp/` that calls
`toolchain_manager.install` directly without also importing from
`toolchain_orchestrator` fails the test.
