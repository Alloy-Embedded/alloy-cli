## ADDED Requirements

### Requirement: the MCP server SHALL expose ``alloy.toolchain_apply_install_plan``

``alloy mcp serve`` SHALL register a new mutating tool
``toolchain_apply_install_plan`` that complements Wave 2's
``toolchain_install_plan`` (read-only).  The tool's parameter
schema SHALL declare a single required ``family_id: string``
argument.

The handler SHALL dispatch through
``toolchain_orchestrator.install_family`` and return a JSON-friendly
payload of the same shape across calls:

```
{
  "family_id": "stm32g0",
  "host": {"os": "macos", "arch": "arm64"},
  "outcomes": [
    {"tool": "...", "version": "...", "sha256": "...",
     "skipped": false, "reason": "installed",
     "bytes_downloaded": 280123456,
     "store_path": "..."},
    {"tool": "STM32CubeProgrammer", "version": "...",
     "skipped": true, "reason": "vendor",
     "install_doc_url": "https://www.st.com/..."}
  ],
  "total_bytes_downloaded": 290000000,
  "lockfile_updated": true
}
```

Idempotency SHALL be preserved: re-calling the tool on a fully-
installed family returns every outcome with ``skipped=true,
reason="already-installed"`` and ``total_bytes_downloaded=0``.
Vendor tools SHALL surface with ``skipped=true, reason="vendor"``
and a populated ``install_doc_url``; the handler SHALL NEVER
spawn a download for them.

The MCP system prompt (``src/alloy_cli/integrations/opencode/
system_prompt.md``) SHALL document the two-phase contract:
agents call ``toolchain_install_plan`` first, surface the plan
to the user, get explicit confirmation, then call
``toolchain_apply_install_plan``.  The Wave 1 ``preview_diff →
apply_diff`` pattern is the precedent; the same operating
principle applies here.

Errors SHALL propagate via the typed envelope.  Wave-2's
``family-toolchain-installer-{checksum,download,extract,
locked,store-corrupt,version-mismatch,unsupported-host}``
flow up unchanged.  Wave 3's
``onboarding-cancelled`` SHALL NOT be raised here — the MCP
caller cannot mid-cancel; the tool runs to completion or fails
typed.

#### Scenario: apply_install_plan installs every non-vendor tool

- **WHEN** an MCP client calls
  ``alloy.toolchain_apply_install_plan(family_id="stm32g0")``
- **AND** the toolchain store is empty
- **THEN** the response SHALL list every required + recommended
  non-vendor tool with ``skipped=false, reason="installed"``
- **AND** each entry SHALL carry ``store_path`` (absolute) +
  ``bytes_downloaded`` (>0)
- **AND** ``total_bytes_downloaded`` SHALL be the sum of every
  entry's ``bytes_downloaded``
- **AND** ``lockfile_updated`` SHALL be true (the project has a
  fresh ``.alloy/toolchain.lock`` after the call)

#### Scenario: re-calling apply_install_plan is idempotent

- **WHEN** an MCP client calls ``apply_install_plan`` twice in a
  row on the same family
- **THEN** the second response SHALL list every entry with
  ``skipped=true, reason="already-installed"``
- **AND** ``total_bytes_downloaded`` SHALL be 0
- **AND** no network call SHALL be made on the second invocation
  (verifiable by swapping in an exploding downloader)

#### Scenario: vendor tool is reported, never installed

- **WHEN** an MCP client calls ``apply_install_plan(family_id=
  "stm32f4")``
- **THEN** ``STM32CubeProgrammer`` SHALL appear in ``outcomes``
  with ``skipped=true, reason="vendor"``
- **AND** the entry SHALL include ``install_doc_url``
- **AND** the install_doc_url SHALL be the per-active-OS URL
  from the family manifest's ``install_docs`` block
- **AND** the downloader SHALL NOT be invoked for that tool

#### Scenario: install failure surfaces a typed envelope

- **WHEN** an MCP client calls ``apply_install_plan`` and one
  tool's downloader returns a corrupt artefact
- **THEN** the corresponding outcome row SHALL carry
  ``skipped=false, reason="failed",
  error_type="family-toolchain-installer-checksum"``
- **AND** the rest of the walk SHALL still complete (other tools
  install successfully)
- **AND** ``lockfile_updated`` SHALL still be true (the lockfile
  reflects the tools that DID succeed)

#### Scenario: tool list includes apply_install_plan on discovery

- **WHEN** an MCP client requests the tool list via ``list_tools``
- **THEN** the returned set SHALL include
  ``toolchain_apply_install_plan``
- **AND** the parameter schema SHALL declare ``family_id``
  as required
- **AND** the description SHALL document the
  ``toolchain_install_plan → toolchain_apply_install_plan``
  preview/confirm pattern
