## Context

Wave 2 (`add-toolchain-installer`) shipped the engine.  Today, a
post-Wave-2 user runs:

```sh
alloy new firmware --board nucleo_g071rb     # scaffolds project
alloy toolchain install                       # has to remember this
alloy build                                   # finally
```

That's two correct commands too many.  Worse, ``alloy doctor --fix``
detects the missing tools but still tells the user to run
``alloy toolchain install`` themselves — a false sense of "the
doctor will handle it."  Five-minutes-to-first-ELF dies on those
two cliffs.

Wave 3 makes the install offer happen automatically at the
right moments:

- After ``alloy new`` (the scaffold knows the family the moment
  it writes ``alloy.toml``; offering the install one prompt later
  is free).
- During ``alloy doctor --fix`` (the doctor already lists what's
  missing; installing it is the obvious next step).
- Through ``alloy setup`` (the friendliest entry point for a fresh
  machine).
- In the TUI Onboarding screen (Wave 1 promised it; Wave 3
  delivers).
- Through the MCP write tool (LLM agents need a way to apply the
  preview from Wave 2's ``toolchain_install_plan``).

Five entry points, one core walk.  The shared orchestrator is the
contract that keeps them honest.

## Goals / Non-Goals

**Goals:**

- One core walk implemented once in ``core.toolchain_orchestrator``.
  Five UI shells call it.  Tests that pin the walk's behaviour run
  without a TTY, without Textual, without subprocess.
- ``alloy new --board <id>`` in a TTY → "Install toolchain now? [Y/n]"
  → user types Y → working toolchain.  Total interactive cost: one
  prompt.
- ``alloy doctor --fix`` becomes the "do everything" command: every
  non-vendor missing tool installs in sequence, vendor tools render
  as info+link (Wave-1 contract preserved).
- ``alloy setup`` is the friendliest entry point.  No project? It
  scaffolds.  Half-installed? It finishes.  Fully set up? It
  prints "next steps" instead of doing nothing.
- The MCP write tool follows the same two-phase pattern as
  ``preview_diff → apply_diff`` for peripheral edits.  LLM agents
  call ``toolchain_install_plan`` first, then
  ``toolchain_apply_install_plan`` after human confirmation.
- Vendor tools NEVER auto-install across any of the five entry
  points.  The orchestrator short-circuits them; the UIs
  surface the install_doc URL.

**Non-Goals:**

- *No new download / extract / SHA-verify code.*  The orchestrator
  delegates to ``toolchain_manager.install`` and
  ``tool_sources.adapter_for``.  Wave 2's atomic pipeline is the
  contract.
- *No resumable wizard sessions.*  If the user Ctrl-Cs mid-install,
  the partial state is whatever Wave-2's atomic install left
  behind (cleaned via ``store/.tmp`` sweep on the next run).
  Wave 4 may add a ``WizardSession`` typed dataclass with explicit
  resume support.
- *No retry policy beyond Wave 2's single retry-with-backoff.*
  The orchestrator surfaces failures as typed errors and lets the
  caller retry the whole walk if it wants.
- *No new family-detection heuristics.*  ``alloy setup`` for a
  project-less directory uses ``alloy boards`` + the existing
  family map; no clever sniffing of binaries on disk or USB.
- *No write to user shell rc files.*  The wizard's "next steps"
  are printed for the user to copy or read; we never edit
  ``~/.zshrc`` etc.

## Decisions

### D1: Shared orchestrator is a Pure Function — `install_family(...) -> InstallReport`

```python
def install_family(
    manifest: FamilyManifest,
    *,
    project_root: Path | None = None,
    include_optional: bool = False,
    force: bool = False,
    on_event: Callable[[InstallEvent], None] | None = None,
    downloader: Downloader | None = None,
) -> InstallReport
```

The function never touches ``input()``, ``Console``, ``Textual``, or
``sys.stdin``.  Progress is surfaced through ``on_event`` callbacks
that emit typed dataclass events:

- ``ToolStarted(tool, version, source, url, size_bytes)``
- ``ToolSkippedVendor(tool, version, install_doc_url)``
- ``ToolSkippedHostUnsupported(tool, host, supported_hosts)``
- ``ToolDownloaded(tool, bytes)``
- ``ToolInstalled(tool, version, sha, store_path, udev_rules_path?)``
- ``ToolFailed(tool, error_type, message)``

CLI shells map events to Rich progress; the TUI maps them to
Textual progress widgets; the MCP tool collects them into a flat
list of ``InstallOutcome`` records.

**Alternatives considered:**

- *Generator that yields events.*  Rejected: callbacks compose
  better with the TUI's async event loop and the MCP's
  request-response shape.  Generators would force every consumer
  to drive iteration in lock-step with the install.
- *Inheritance + abstract render hooks.*  Rejected: adds
  ceremony for no testability gain.  Plain callbacks + frozen
  dataclasses follow the rest of the codebase's Wave-1/2 style.

### D2: Lockfile updates are the orchestrator's responsibility

The orchestrator writes ``.alloy/toolchain.lock`` on success, with
the same ``(tool, version, sha)`` triple per installed tool.
``--shared`` callers (today only ``alloy toolchain install
--shared``) pass ``project_root=None`` to skip the lockfile write.

This means ``alloy new``'s post-scaffold install always lands a
lockfile (the project is freshly born; no surprise overwrites).
``alloy doctor --fix`` writes the lockfile too — the user opted in
via ``--fix``.  ``alloy setup`` writes when there's a project
context.  The TUI follows the wrapping CLI's choice.

### D3: TTY detection is the gate for ``alloy new``'s default install

```python
def _should_offer_install(*, install_flag: bool | None, tty: bool) -> bool:
    if install_flag is True:
        return True
    if install_flag is False:
        return False
    return tty  # default Y in TTY, default N otherwise
```

CI scripts piping ``alloy new`` through subprocess get
``tty=False``, so they don't hang on a prompt that nobody can
answer.  Interactive users in a real terminal see the prompt with
default Y.  Explicit ``--install-toolchain`` / ``--no-install-toolchain``
override either way.

**Alternatives considered:**

- *Always prompt, fail on non-TTY.*  Rejected: would break every
  existing CI invocation of ``alloy new``.
- *Always install, no flag.*  Rejected: a 280 MB download
  silently triggered by a scaffolding command is hostile.

### D4: ``alloy doctor --fix`` adds one new auto-fixer entry, not a new fixer mode

The existing ``AUTO_FIXERS`` dict maps a check's ``name`` to a
fixer callable.  Wave 3 adds entries keyed on synthetic check
names like ``"toolchain:arm-none-eabi-gcc"`` — generated at
``run()`` time when the check list comes from a family manifest.

Each fixer dispatches the single tool through the orchestrator
(``include_optional=False``, ``force=False``, ``project_root=
project_dir``).  Failures from one fixer DO NOT abort the
``--fix`` pass; the existing ``_run_fixes`` loop already handles
per-fixer failure reporting.

**Alternatives considered:**

- *Single ``"toolchain:install-missing"`` check that batches all
  missing tools.*  Rejected: loses per-tool granularity in the
  ``_print_fix_summary`` table; users want to see which one
  failed.
- *Reuse Wave-2's ``alloy toolchain install`` subprocess.*
  Rejected: introduces a process boundary that breaks the
  ``CommandRunner`` test seam.

### D5: ``alloy setup`` is a top-level verb, not a flag on ``alloy new``

Two reasons.  First, ``alloy setup`` is a useful command on a
machine that doesn't have a project yet (clone an existing repo,
``cd`` in, run setup; it scaffolds nothing but ensures the
toolchain matches the lockfile).  Second, mixing ``alloy new``
with project-less wizard logic would balloon ``commands/new.py``
beyond what one file should hold.

The verb's surface:

```sh
alloy setup [--board <id>] [--family <id>] [--auto] [--no-tui]
            [--project-dir <path>]
```

Default project-dir is CWD.  ``--auto`` short-circuits every
prompt with the default answer.  ``--no-tui`` forces the line-
based prompt even when STDIN is a TTY.

### D6: TUI ``OnboardingScreen`` shares widgets with ``DashboardScreen``

The plan-table widget reuses ``Table`` from
``rich.table`` (already imported) for the static plan view, and
introduces a new ``InstallProgressWidget`` (Textual ``Container``
+ ``ProgressBar`` per tool) for the live phase.  Both consume the
same ``InstallEvent`` stream the CLI uses, so the orchestrator's
single emission code path drives them.

The screen's lifecycle:

1. ``compose()`` — render the family-picker step OR auto-detect
   from the project.
2. On family confirmation → render the plan table.
3. On user "Install" button press → spawn the orchestrator on a
   worker thread.  The orchestrator emits events; the screen
   pumps them through its message queue into widget updates.
4. On final event → render the "All set" panel with copyable
   "Try alloy build" command.

Errors (``ToolFailed``) render as a per-row red badge; the user
can dismiss the row and continue, OR cancel the whole wizard.
Cancelling raises ``OnboardingCancelledError`` from the calling
context (``alloy setup`` / ``alloy new``); the CLI exits 130
(SIGINT convention) so scripts can detect it.

### D7: MCP write tool mirrors the install flow shape

```python
{
  "family_id": "stm32g0",
  "host": {"os": "macos", "arch": "arm64"},
  "outcomes": [
    {
      "tool": "arm-none-eabi-gcc",
      "version": "14.2.1-1.1",
      "sha256": "abc...",
      "skipped": false,
      "reason": "installed",
      "bytes_downloaded": 280123456,
      "store_path": "/Users/lgili/.local/share/alloy/tools/store/abc..."
    },
    {
      "tool": "STM32CubeProgrammer",
      "version": "2.16",
      "skipped": true,
      "reason": "vendor",
      "install_doc_url": "https://www.st.com/..."
    }
  ],
  "total_bytes_downloaded": 290000000,
  "lockfile_updated": true
}
```

The agent treats ``skipped + reason="vendor"`` as "show the user
the URL"; ``skipped + reason="already-installed"`` as a no-op
(idempotency); ``error_type="..."`` envelopes as install failures
that can be retried by re-calling the same tool.

### D8: Family detection in ``alloy setup`` reuses Wave-1 helpers

When the user runs ``alloy setup`` outside a project, the verb
prompts for a board id from a curated list (the existing
``alloy boards`` catalog, sorted by tier).  The selected board's
manifest pins the family.  Inside a project, ``setup`` resolves
the family the same way ``alloy doctor`` does in Wave 1 (chip /
board → family).  No new heuristics.

### D9: ``OnboardingCancelledError`` is the only new error type

Most failure modes already have a Wave-2 typed error
(``family-toolchain-installer-*``).  The one Wave 3 introduces:
``OnboardingCancelledError`` for "user pressed Ctrl-C / clicked
Cancel mid-wizard".  It carries the partial outcomes so the CLI
can surface "X tools installed before you cancelled" without
losing context.

The ``error_type`` string is ``"onboarding-cancelled"`` (the
Wave-1 pattern of ``"family-toolchain-*"`` is reserved for
toolchain content errors).

## Risks / Trade-offs

- **[Risk]** A user runs ``alloy new`` in a TTY with no network
  and answers Y → install fails partway through.
  → **Mitigation**: orchestrator emits ``ToolFailed`` events; CLI
  prints the summary at the end with the actionable
  ``Run alloy toolchain install`` retry command.  Wave 2's
  per-tool atomicity ensures the partial state is consistent.

- **[Risk]** ``alloy doctor --fix`` becomes the "everything"
  hammer; users stop running ``alloy toolchain install``
  themselves.
  → **Accepted**: that's the goal.  ``alloy toolchain install``
  remains as the explicit / scriptable verb; ``--fix`` is the
  friendly umbrella.

- **[Risk]** The TUI Onboarding screen depends on Textual's
  threading model; race conditions between the worker and the UI
  are notoriously hard to reproduce.
  → **Mitigation**: snapshot tests pin the expected SVG render
  for each event class (started / downloaded / installed /
  failed); the actual threading is exercised by Wave-1's TUI
  smoke tests.

- **[Risk]** ``alloy setup`` outside a project becomes a
  "second front door" people use INSTEAD of ``alloy new``;
  the two diverge over time.
  → **Mitigation**: ``alloy setup`` for a fresh machine without
  a project simply embeds the ``alloy new`` flow (calls into
  ``commands.new._scaffold_then_install`` directly).  No new
  scaffolding code path.

- **[Risk]** A non-TTY user pipes ``alloy new`` through
  ``< /dev/null`` to suppress the prompt → install never
  triggers, user confused.
  → **Mitigation**: the post-scaffold output ALWAYS prints the
  next-step command, regardless of the install decision.  The
  user always sees ``Run \`alloy toolchain install\` next.``
  in the output.

- **[Risk]** MCP ``apply_install_plan`` lets an LLM trigger
  multi-hundred-MB downloads.
  → **Mitigation**: agents are instructed (system prompt) to
  call ``toolchain_install_plan`` first and confirm with the
  human BEFORE calling ``toolchain_apply_install_plan``.  The
  tool's docstring restates the contract.  Wave-2's lock file
  ensures concurrent runs serialise.

- **[Trade-off]** Wave 3 doesn't add resumable wizards.  A user
  who cancels mid-install loses the prompts for the remaining
  tools and must run ``alloy toolchain install`` to finish.
  → **Accepted**: resumability is a Wave-4 concern when the
  recovery commands also need to checkpoint state (``alloy
  recover --resume``).  Wave 3's atomic per-tool installs are
  the floor.

## Migration Plan

Purely additive at the user surface.  No deprecations, no breaking
changes.  Roll-out per task block in tasks.md:

1. Land the orchestrator + tests.  No external surface change.
2. Land ``alloy new``'s flags + prompt.
3. Land the doctor ``--fix`` extension.
4. Land ``alloy setup``.
5. Land the TUI Onboarding screen.
6. Land the MCP apply tool.
7. Land docs + cheatsheet regen.
8. Validate + CHANGELOG.

Rollback per block: each is independently revertable.  The
orchestrator (block 1) is consumed by every later block, so
reverting it forces reverting blocks 2-6 together — but the data
+ docs land independently.

## Open Questions

- **Q1**: Should ``alloy setup`` accept ``--family`` in addition
  to ``--board``?  Useful when the user knows their MCU but
  doesn't see a curated board for it.
  → *Proposed answer*: yes.  Mirrors ``alloy doctor --for``;
  zero new code (we already validate family ids in the doctor
  CLI).

- **Q2**: Does the post-``alloy new`` prompt also offer codegen
  setup (``alloy build`` warm-up)?  Wave 1 didn't add that hook.
  → *Deferred*: out of scope.  Wave 4 (or a follow-up) can
  unify "scaffold + toolchain + first build" if users ask for
  it.  Wave 3 stops at toolchain installed.

- **Q3**: For the TUI screen, do we need a ``--no-install``
  fallback for users who only want to browse the plan?
  → *Proposed answer*: the screen's "Cancel" button raises
  ``OnboardingCancelledError`` cleanly; that doubles as
  "browsed, didn't install."  No separate flag needed.

- **Q4**: Should ``alloy doctor --fix`` install ``recommended``
  tools too, or only ``required``?
  → *Proposed answer*: required only by default; gate
  recommended behind a ``--with-recommended`` flag.  Same
  posture as ``alloy toolchain install --include-optional``.
