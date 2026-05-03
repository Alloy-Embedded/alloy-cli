# Toolchain Installer — `data/sources/*.json` + `core.toolchain_manager`

Wave 2 of the toolchain-management track turns
[Wave 1's per-family manifests](TOOLCHAIN_REGISTRY.md) into an actual
**binary installer**.  alloy-cli downloads, verifies-by-SHA256,
extracts, and self-hosts every non-vendor tool a project's family
declares — without ever touching the user's `PATH`.  Build / flash /
debug invocations pick up the cached binaries through absolute paths
in a generated CMake toolchain file and direct subprocess arguments.

> Vendor (EULA-gated) tools — STM32CubeProgrammer, nrfjprog, J-Link,
> Atmel Studio — STAY detect+link only.  The installer never touches
> them; Wave 1's renderer keeps owning that flow.

This document is the **contributor reference** for the source-pin
format, the content-addressed store, the lockfile workflow, and
the trust model.  User-facing docs live alongside `alloy toolchain
--help` and the [cheatsheet](CHEATSHEET.md).

## Why this exists vs. Wave 1

Wave 1 (`add-toolchain-registry`) shipped the **map**:
`data/families/<family>.yml` declares which tools each MCU family
needs.  `alloy doctor` lists what's missing; the user copy-pastes a
`brew install ...` line and worries about PATH conflicts themselves.

Wave 2 ships the **install**: alloy-cli fetches the binaries directly
into a hermetic store at `platformdirs.user_data_dir("alloy")/tools/`,
content-addressed by SHA256, and the build pipeline picks them up via
an auto-generated CMake toolchain file.  Three guarantees shape the
implementation:

1. **PATH stays the user's.**  We write nothing to `~/.zshrc` /
   `~/.bashrc` / etc.  The store lives entirely under platformdirs;
   CMake / probe-rs / gdb invocations reference it by absolute path.
2. **No URL is followed without a matching SHA256.**  Every URL the
   runtime fetches comes from `data/sources/*.json`, committed to the
   repo and reviewed at PR time.  Streaming SHA verification refuses
   to finalise a tampered tarball.
3. **EULA-gated tools never auto-install.**  `source: vendor` from
   Wave 1's manifests means "render the install_doc URL" — Wave 2
   skips them in `alloy toolchain install` with an explicit
   "skipped (vendor — install manually)" line.

## Architecture (tl;dr)

```
data/families/<family>.yml          ← Wave 1: which tools per family
        │
        ▼
core.toolchain_registry             ← Wave 1: typed loader
        │
        ▼
core.tool_sources                   ← Wave 2: adapter layer
  • XpackAdapter  → data/sources/xpack.json
  • GithubAdapter → data/sources/github.json
  • ProbeRsAdapter → data/sources/probe-rs.json
  • EspressifAdapter → data/sources/espressif.json
  • Downloader (stdlib urllib + streaming SHA256)
        │
        ▼
core.toolchain_manager              ← Wave 2: content store
  • install / resolve / list / verify / prune
  • by-name/<tool>/<v> → store/<sha256>/
  • manifest.json + .lock advisory file lock
        │
        ├─────────────────┬──────────────────┐
        ▼                 ▼                  ▼
core.build           core.flash         alloy toolchain (CLI)
  toolchain.cmake     resolve_for_         install / list /
  CMAKE_C_COMPILER    lockfile()           use / prune / shell
```

## Pin file format (`data/sources/*.json`)

Every URL alloy-cli fetches at runtime comes from one of these JSON
files.  Validated at load time against
[`schema/source_manifest_v1.json`](../schema/source_manifest_v1.json)
(JSON Schema Draft 2020-12).

```json
{
  "schema_version": "1.0.0",
  "source": "xpack",
  "_pending_verification": true,
  "_notes": "Optional contributor-facing free-text.",
  "tools": [
    {
      "tool": "arm-none-eabi-gcc",
      "version": "14.2.1-1.1",
      "udev_rules": "...",
      "hosts": {
        "macos-arm64": {
          "url": "https://github.com/xpack-dev-tools/.../arm-gcc.tar.gz",
          "sha256": "abc...",
          "archive_kind": "tar.gz",
          "extract_to_subdir": "xpack-arm-none-eabi-gcc-14.2.1-1.1",
          "binaries": ["bin/arm-none-eabi-gcc", "bin/arm-none-eabi-gdb"],
          "size_bytes": 280000000
        }
      },
      "unsupported_hosts": ["linux-arm64"]
    }
  ]
}
```

### Top-level fields

| Field | Required | Meaning |
|-------|----------|---------|
| `schema_version` | ✅ | SemVer of the manifest schema (always `"1.0.0"` until additive bump). |
| `source` | ✅ | Closed enum: `xpack`, `github`, `probe-rs`, `espressif`.  **NEVER** `vendor` — vendor tools live only in family manifests with their per-OS install_docs. |
| `tools` | ✅ | Array of tool pins (`tools[]`); at least one entry. |
| `_pending_verification` | ❌ | When `true`, `sha256` fields are placeholders awaiting `scripts/refresh_source_pins.py`. |
| `_notes` | ❌ | Contributor free-text (e.g. how URLs were sourced). |

### Per-tool fields

| Field | Required | Meaning |
|-------|----------|---------|
| `tool` | ✅ | Canonical tool name (matches the family manifest's `tool`). |
| `version` | ✅ | Exact SemVer-ish pin (no ranges).  Accepts `_` as suffix separator for vendor stamps like Espressif's `14.2.0_20240906`. |
| `hosts` | ✅ | Map of `<os>-<arch>` → host artefact.  At least one entry. |
| `udev_rules` | ❌ | Linux udev rules text (required when the family manifest declares `udev_required: true`). |
| `unsupported_hosts` | ❌ | Host triples upstream does NOT publish (documents the gap). |

### Per-host artefact fields

| Field | Required | Meaning |
|-------|----------|---------|
| `url` | ✅ | `https://...` — http is rejected at schema time. |
| `sha256` | ✅ | Lower-case hex SHA-256 (64 chars).  Zero-padding is allowed only when the parent file declares `_pending_verification: true`. |
| `archive_kind` | ✅ | `tar.xz` / `tar.gz` / `tar.bz2` / `zip` / `bin` (single-file binary). |
| `extract_to_subdir` | ❌ | Top-level dir inside the archive (xpack convention).  The manager flattens it into the store root. |
| `binaries` | ✅ | Array of relative paths (`binaries[]`) the consumers reach for.  First entry is the canonical primary.  Bundled binaries (e.g. gdb shipped with gcc) appear as additional entries. |
| `size_bytes` | ❌ | Optional; used by `--dry-run` to compute total download size. |

### Host triple format

Closed enum: `(linux|macos|windows)-(x86_64|arm64)`.  New arches
require a schema bump.  Aliases (`AMD64` → `x86_64`, `aarch64` →
`arm64`) are mapped at `host_triple()` call time.

## Source adapter contract

Each adapter implements a single-method protocol:

```python
class Source(Protocol):
    @property
    def kind(self) -> str: ...
    def resolve(
        self, tool: ToolRequirement, host: HostTriple
    ) -> SourceArtifact: ...
```

Adapters are **pure**: construction never touches the network, the
filesystem outside `data/sources/`, or environment variables.  The
dispatcher (`core.tool_sources.adapter_for`) maps the manifest's
`source` string to the right adapter:

| `source` string | Adapter | Pin file |
|-----------------|---------|----------|
| `xpack` | `XpackAdapter` | `data/sources/xpack.json` |
| `github:<owner>/<repo>` | `GithubAdapter` | `data/sources/github.json` |
| `probe-rs-installer` | `ProbeRsAdapter` | `data/sources/probe-rs.json` |
| `espressif` | `EspressifAdapter` | `data/sources/espressif.json` |
| `vendor` | (raises) | — |

Adding a new source is one new adapter class + one new JSON file +
one entry in `_SOURCE_KIND_TO_FILENAME`.

## Content-addressed store layout

Resolved by `platformdirs.user_data_dir("alloy")` (overridable via the
`ALLOY_TOOLS_ROOT` environment variable for tests / CI):

```
<base>/alloy/tools/
├── store/<sha256>/                 # extracted artefact, immutable
├── store/.tmp/<sha256>.archive     # in-flight download
├── store/.tmp/<sha256>/            # in-flight extraction
├── by-name/<tool>/<version>        # symlink → ../../store/<sha256>   (POSIX)
├── by-name/<tool>/<version>/_pointer.txt   # text pointer file (Windows)
├── manifest.json                   # registry of installed tools
├── udev/<tool>.rules               # Linux probe rules awaiting `sudo cp`
└── .lock                           # advisory file lock (fcntl / msvcrt)
```

Content addressing: two projects pinning the same `(tool, version,
host)` share one extraction.  The `by-name/<tool>/<version>` slot is
the human-friendly view; on POSIX it's a symlink, on Windows it's a
tiny pointer file the manager dereferences.

## Atomic install pipeline

`core.toolchain_manager.install(artifact)` runs:

1. Acquire `.lock` (`fcntl.flock` POSIX / `msvcrt.locking` Windows).
   Held? → `family-toolchain-installer-locked`.
2. Sweep stale `.tmp/` (>1h old) so a previous-run kill doesn't leak.
3. Idempotency check: same `(tool, version, sha)` already promoted
   → `InstallOutcome(skipped=True)`, no network.
4. Stream download → SHA verify on the wire → write to
   `.tmp/<sha>.archive`.  Mismatch → typed
   `family-toolchain-installer-checksum`, no extraction.
5. Extract into `.tmp/<sha>/`.  Path-traversal members are rejected
   via `tarfile.data_filter` (Py 3.12+) or manual sanitisation.
6. Flatten `extract_to_subdir` if declared.
7. `os.rename(.tmp/<sha>, store/<sha>)` — atomic commit boundary.
8. Drop `by-name/<tool>/<version>` symlink (or pointer file).
9. Write Linux udev rules to `<base>/alloy/udev/<tool>.rules` and
   emit the explicit `sudo cp ... && sudo udevadm control
   --reload-rules` instruction.  **Never invokes sudo.**
10. Update `manifest.json` atomically (.tmp + os.rename).

## Project lockfile (`.alloy/toolchain.lock`)

Pins the exact `(version, sha256)` per tool the project consumes.
TOML, deterministic emission via `lockfile_toolchain.dumps`:

```toml
schema_version = "1.0.0"

[tools]
"arm-none-eabi-gcc" = { version = "14.2.1-1.1", sha256 = "abc..." }
"probe-rs"          = { version = "0.27.0", sha256 = "def..." }
```

API: `core.lockfile_toolchain.{read, write, parse, dumps, add,
remove, diff, empty, read_optional}` — every function takes / returns
a frozen `ToolchainLock`, so two callers can never drift.

## CMake toolchain file generation

When the project carries `.alloy/toolchain.lock`, `core.build.run`
writes `.alloy/cache/toolchain.cmake` and passes
`-DCMAKE_TOOLCHAIN_FILE=...` to cmake configure.  Generation is
stamp-keyed on `sha256(lockfile_text) + alloy_cli_version`, mirroring
the codegen stamp pattern.

The toolchain file sets `CMAKE_C_COMPILER`, `CMAKE_CXX_COMPILER`,
`CMAKE_ASM_COMPILER`, `CMAKE_AR`, `CMAKE_RANLIB`, etc. to absolute
paths inside the store.  The compiler-family map lives in
`_COMPILER_FAMILIES` at the top of `core.build`; new compiler
families (e.g. `clang-arm-embedded`) are one entry there + a pin
file row.

When no lockfile exists, the toolchain file is NOT generated and
cmake falls back to PATH resolution — byte-identical to the
pre-Wave-2 baseline.

## Trust model

Three explicit boundaries:

1. **The pin files (`data/sources/*.json`).**  Reviewed at PR time.
   `scripts/refresh_source_pins.py` only writes to disk; it never
   pushes commits or opens PRs automatically.
2. **The download stream.**  Streaming SHA verification refuses to
   finalise a tampered artefact before any byte lands on disk.
   TLS via stdlib `urllib.request` honours system trust roots; no
   verification disablement, no follow-redirect to non-pinned hosts.
3. **The extraction.**  `tarfile.data_filter` (Py 3.12+) rejects
   absolute paths and `..`-traversal.  Older Pythons get a manual
   scrub pass that's exercised by `test_path_traversal_in_archive_rejected`.

We explicitly do NOT trust:

- The user's `PATH` (compilers come from the store).
- Their TLS proxy (we don't disable verification — set
  `SSL_CERT_FILE` / `SSL_CERT_DIR` for enterprise CAs).
- Upstream URLs we haven't pinned (every URL crosses
  `data/sources/*.json` first).

## Refreshing the pinned URL+SHA tables

`scripts/refresh_source_pins.py` walks every `data/sources/*.json`
file, downloads each pin's URL for the active host (or all hosts
when running on a CI matrix), recomputes SHA256, and updates the
JSON in place.

```sh
# Default: dry-run.  Prints the diff; writes nothing.
python scripts/refresh_source_pins.py

# Apply the diff to data/sources/*.json on disk.
python scripts/refresh_source_pins.py --apply

# Filter to a specific source kind.
python scripts/refresh_source_pins.py --source xpack --apply

# Filter by tool.
python scripts/refresh_source_pins.py --tool arm-none-eabi-gcc --apply
```

Failures (HTTP errors, network flakes) are warnings, not blockers —
the script reports the failure per pin and continues.  When all pins
succeed AND the file no longer needs `_pending_verification`, the
script flips the flag to `false` automatically.

The script is meant to be run **periodically** (or after authoring a
new pin), with output reviewed manually before commit.  It NEVER
opens a PR.

## Add a new source — walkthrough

You want to ship pins for an upstream alloy-cli doesn't currently
support (e.g., `microchip-cube` for SAM-BA / Atmel Studio downloads)?

1. **Pick the source kind**.  Lower-case, kebab-friendly identifier
   that maps to the manifest's `source` field.

2. **Author the pin file** at `data/sources/<kind>.json`.  Copy
   `data/sources/github.json` as a template and adjust.

3. **Add the adapter class** in
   [`src/alloy_cli/core/tool_sources.py`](../src/alloy_cli/core/tool_sources.py):

   ```python
   class MyVendorAdapter(_BaseAdapter):
       """Resolves <vendor>'s release feed."""
       KIND = "my-vendor"
   ```

4. **Wire the dispatcher**.  Add the entry in `_SOURCE_KIND_TO_FILENAME`
   and the `if/elif` chain in `adapter_for(...)`.

5. **Update the family manifest(s)** to use the new source string.

6. **Validate locally**:

   ```sh
   .venv/bin/pytest tests/test_source_manifest_schema.py
   .venv/bin/pytest tests/test_tool_sources.py
   ```

7. **Add tests**.  Mirror the existing `test_xpack_adapter_*` tests in
   `tests/test_tool_sources.py`.

8. **Open the PR**.  CI runs `openspec validate --strict`, `pytest`,
   `ruff`, and `pyright`.

## Errors

Every failure path raises a typed error from
`AlloyCliError → FamilyToolchainInstallerError`:

* [`family-toolchain-installer-error`](ERROR_COOKBOOK.md#family-toolchain-installer-error)
  — base type for the installer.
* [`family-toolchain-installer-checksum`](ERROR_COOKBOOK.md#family-toolchain-installer-checksum)
  — downloaded SHA didn't match the pin.  Re-run, or refresh pins.
* [`family-toolchain-installer-download`](ERROR_COOKBOOK.md#family-toolchain-installer-download)
  — HTTP / network failure.
* [`family-toolchain-installer-extract`](ERROR_COOKBOOK.md#family-toolchain-installer-extract)
  — corrupt archive or path-traversal attempt.
* [`family-toolchain-installer-store-corrupt`](ERROR_COOKBOOK.md#family-toolchain-installer-store-corrupt)
  — manifest references a missing extraction.
* [`family-toolchain-installer-version-mismatch`](ERROR_COOKBOOK.md#family-toolchain-installer-version-mismatch)
  — lockfile pins a `(version, sha)` not in the store.
* [`family-toolchain-installer-unsupported-host`](ERROR_COOKBOOK.md#family-toolchain-installer-unsupported-host)
  — active host triple has no pin for the requested tool.
* [`family-toolchain-installer-locked`](ERROR_COOKBOOK.md#family-toolchain-installer-locked)
  — another alloy-cli process holds the store lock.

## Related references

* [`docs/TOOLCHAIN_REGISTRY.md`](TOOLCHAIN_REGISTRY.md) — Wave 1's
  family manifest format.
* [`schema/source_manifest_v1.json`](../schema/source_manifest_v1.json)
  — the authoritative pin file schema.
* [`schema/family_toolchain_v1.json`](../schema/family_toolchain_v1.json)
  — the authoritative family manifest schema (Wave 1).
* [`src/alloy_cli/core/tool_sources.py`](../src/alloy_cli/core/tool_sources.py)
  — adapters + Downloader.
* [`src/alloy_cli/core/toolchain_manager.py`](../src/alloy_cli/core/toolchain_manager.py)
  — content-addressed store + atomic install.
* [`src/alloy_cli/core/lockfile_toolchain.py`](../src/alloy_cli/core/lockfile_toolchain.py)
  — `.alloy/toolchain.lock` reader/writer.
* [`src/alloy_cli/commands/toolchain.py`](../src/alloy_cli/commands/toolchain.py)
  — the five `alloy toolchain` verbs.
* [`openspec/changes/add-toolchain-installer/`](../openspec/changes/add-toolchain-installer/)
  — the OpenSpec proposal that introduced this capability.
