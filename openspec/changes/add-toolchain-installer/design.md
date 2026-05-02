## Context

Wave 1 (`add-toolchain-registry`) shipped the data and the doctor —
contributors can describe a family's tool surface, and users can see
what they're missing.  The "missing" rows still tell users to copy a
`brew install` line and worry about PATH conflicts themselves.

Today's `core.toolchain` only enumerates `shutil.which`-backed
detectors (`detect_arm_gcc`, `detect_cmake`, …); when a tool is
missing, the user is on their own.  Today's `core.build.run`
implicitly trusts the system PATH for `cmake`, `ninja`,
`arm-none-eabi-gcc`.  Today's `core.flash.run` does the same for
`probe-rs`.  When a user has multiple toolchain versions installed
(common: arm-gcc 13 from one bundle, 14 from another), the
"correct" one wins by `$PATH` ordering, not project intent.

Wave 2 introduces the *install* and *use* layer.  Three guarantees
shape the design:

1. **PATH stays the user's.**  alloy-cli writes nothing to the user's
   shell rc files.  The store lives entirely under
   `platformdirs.user_data_dir("alloy")` and is referenced by
   absolute path from CMake, probe-rs, gdb invocations.
2. **No URL is followed without a matching SHA256.**  Every URL the
   runtime fetches comes from `data/sources/*.json`, which is
   committed to the repository and reviewed at PR time.  An
   adversary tampering with a download mid-flight surfaces as a
   typed `family-toolchain-installer-checksum` error before any
   extraction happens.
3. **EULA-gated tools never auto-install.**  `source: vendor` from
   Wave 1's manifests already means "render an info row with a
   per-OS doc URL"; Wave 2 must skip them in `alloy toolchain
   install` with an explicit "skipped (vendor — install manually)"
   line.

The implementation builds on three existing seams:

- `core.toolchain_registry` (Wave 1) returns the per-family
  `FamilyManifest` with `required[]` and `recommended[]` arrays.
  Wave 2 iterates those arrays and dispatches each non-vendor entry
  to a source adapter.
- `core.process.runner` (CommandRunner protocol) is the seam tests
  monkeypatch for cmake/ninja/probe-rs invocations.  Wave 2 adds
  one parallel seam — `core.tool_sources.Downloader` — that tests
  swap with a fake.
- `core.diagnose` (Wave 1) already renders missing tools with a
  `source` column.  Wave 2 keeps the rendering as-is; only the
  `install_hint` copy changes from "Wave-2 will install via xpack"
  to "run `alloy toolchain install`."

## Goals / Non-Goals

**Goals:**

- A single command — `alloy toolchain install --for <family>` —
  drops every required + non-vendor recommended tool into a
  hermetic store and pins the exact versions in the project's
  `.alloy/toolchain.lock`.
- `alloy build` / `alloy flash` / `alloy debug` automatically pick
  the cached binaries via absolute path; the user never edits PATH.
- Atomic, idempotent, concurrent-safe installs.  Re-running on a
  green install is a no-op; running two installs in parallel from
  different terminals is safe (advisory file lock).
- Cross-platform: macOS arm64 + x86_64, Linux arm64 + x86_64,
  Windows x86_64 from day one.  Other host triples raise a typed
  `family-toolchain-installer-unsupported-host`.
- Garbage collection: `alloy toolchain prune` reclaims store space
  by deleting versions no project's `.alloy/toolchain.lock`
  references.
- Full backward compatibility.  Projects without a lockfile
  continue to build / flash / debug exactly as they do today.

**Non-Goals:**

- *No PATH modification.*  We don't write to `~/.zshrc`,
  `~/.bashrc`, `~/.config/fish/config.fish`, or any user-owned
  shell config file.  `alloy toolchain shell` is the only path
  to a PATH-augmented environment, and it lives only inside the
  spawned subshell.
- *No vendor auto-install.*  STM32CubeProgrammer, nrfjprog, J-Link,
  and any future EULA-gated tool are out of scope for the
  installer.  Wave 1's renderer keeps owning them.
- *No background download daemon, no ambient sync.*  `alloy
  toolchain install` is one CLI invocation that finishes when
  every tarball is on disk.
- *No `alloy doctor --fix` extension this wave.*  Wave 3 wires the
  installer into the `--fix` and `alloy new` flows.  This wave
  ships the building blocks; Wave 3 does the polish.
- *No vendored binaries inside the alloy-cli wheel.*  We ship
  metadata (URLs + SHAs); upstream tarballs are downloaded on
  first install.
- *No HTTP retries beyond a single retry with backoff.*  Network
  flakes surface as a typed error so the user can re-run; we
  don't try to be a download manager.

## Decisions

### D1: Pinned URL+SHA tables ship inside alloy-cli, never resolved at runtime

Every URL the runtime opens MUST be present in `data/sources/*.json`,
which is committed to the alloy-cli repo and validated by JSON Schema
at every load.  At adapter resolve time:

1. Adapter looks up `(tool, version-range, host triple)` in the
   appropriate JSON file.
2. Adapter returns a `SourceArtifact { url, sha256, archive_kind,
   extract_to_subdir, binaries[] }` value.
3. The downloader fetches `url`, computes the SHA256 of the bytes
   on the wire, refuses to write to disk if it doesn't match the
   pinned `sha256`.

**Alternatives considered:**

- *Resolve URLs at runtime via upstream release APIs.*  Rejected:
  GitHub / xpack / Espressif APIs are rate-limited, unreliable
  in CI containers, and put `dl.espressif.com` and `api.github.com`
  on the trust boundary.  Pinning solves all three.
- *Vendor the tarballs inside the alloy-cli wheel.*  Rejected:
  arm-gcc xpack alone is ~280 MB; multiplied by 5 host triples and
  several versions, the wheel would balloon past PyPI's 100 MB
  limit and cripple `pip install alloy-cli`.

### D2: Content-addressed store at `platformdirs.user_data_dir("alloy")/tools/`

Storage layout (resolved by `platformdirs.user_data_dir("alloy")`):

```
<base>/alloy/tools/
├── store/<sha256>/                 # extracted artefact, immutable
├── store/.tmp/<sha256>.partial     # in-flight download; deleted on cleanup
├── store/.tmp/<sha256>/            # in-flight extraction; promoted via os.rename
├── by-name/<tool>/<version>        # symlink → ../../store/<sha256>   (Linux/macOS)
├── by-name/<tool>/<version>/_pointer.txt   # text file with the sha   (Windows)
├── manifest.json                   # registry of installed tools
├── udev/<tool>.rules               # Linux probe rules awaiting `sudo cp`
└── .lock                           # advisory POSIX file lock
```

Content addressing means two projects pinning the same `(tool,
version, host)` share one extraction.  The `by-name/<tool>/<version>`
slot is the human-friendly view that consumers (CMake, probe-rs,
gdb) reach for; on POSIX it's a symlink, on Windows it's a tiny
pointer file the manager dereferences.

**Alternatives considered:**

- *Per-project install (under `.alloy/tools/`).*  Rejected: forces
  every clone of the same project to re-download.  We pin per
  project (lockfile) but share the bytes globally.
- *Hash the URL instead of the bytes.*  Rejected: vendor URLs
  occasionally change without a content change (e.g., a CDN
  rewrite); content-addressing on bytes makes that a no-op.

### D3: Atomic install via `os.rename` + advisory flock

Install steps for one tool:

1. Acquire `.lock` (POSIX: `fcntl.flock(LOCK_EX | LOCK_NB)`,
   Windows: `msvcrt.locking`).  If already locked by another
   process, raise `family-toolchain-installer-locked` so the
   user can retry.
2. Check `manifest.json` — if `(tool, version, sha256)` is
   already promoted, return `InstallOutcome(skipped=True)`.
3. Stream the URL into `store/.tmp/<sha>.partial`, hashing on
   the fly.  Refuse to write the final byte if the running hash
   diverges from the pin.  Cleanup `.partial` on any error.
4. Extract into `store/.tmp/<sha>/`.  If extraction fails
   (corrupt archive, disk full), clean up and raise.
5. `os.rename(store/.tmp/<sha>, store/<sha>)`.  rename is
   atomic on the same filesystem.
6. Update `by-name/<tool>/<version>` (symlink or pointer file).
7. Update `manifest.json` under the same lock.
8. Release `.lock`.

The `os.rename` step is the commit boundary.  If alloy-cli is
killed before step 5, the partial files in `store/.tmp/` are
swept by the next install (any `.tmp` entry older than 1h gets
deleted at install-start).  If killed after step 5 but before
step 7, the next install detects the orphaned `store/<sha>/`
without a manifest entry and rebuilds the manifest.  Either way,
the user sees consistent state.

**Alternatives considered:**

- *Database (SQLite) for manifest.json.*  Rejected: a single
  JSON file is enough for ≤200 entries (our worst-case fleet
  count over the next two years), and round-trips through
  `json.dumps(sort_keys=True)` are diff-friendly.
- *Compute SHA256 only after the full download.*  Rejected:
  forces us to write potentially-malicious bytes to disk before
  validation.  Streaming-hash + refuse-to-finalise is strictly
  safer.

### D4: Per-project lockfile separate from `version.lock`

`.alloy/toolchain.lock` (TOML) pins the tool versions THIS project
uses.  Format:

```toml
schema_version = "1.0.0"
[tools]
"arm-none-eabi-gcc" = { version = "14.2.0", sha256 = "abc..." }
"probe-rs"          = { version = "0.27.0", sha256 = "def..." }
```

Why a separate file from `version.lock` (which already pins
alloy-cli, alloy-codegen, alloy-devices-yml, and the alloy HAL)?

- They have different cadences.  A user can switch from arm-gcc
  14.2 → 14.3 without bumping any alloy ecosystem component.
- The toolchain lock is used by `alloy build` / `alloy flash` to
  resolve binaries.  `version.lock` is used to FetchContent the
  HAL.  Co-locating them couples two unrelated decisions.
- The diff for `git blame` on `toolchain.lock` is then a clean
  history of "I upgraded arm-gcc on date X."

**Alternatives considered:**

- *Merge into `alloy.toml` under a `[toolchain]` section.*
  Rejected: lockfiles are auto-generated; `alloy.toml` is
  human-edited.  Mixing them invites accidental edits.
- *Merge into `version.lock`.*  Rejected as above (different
  cadences).

### D5: CMake toolchain file is generated, not hand-written

`core.build.run` writes `.alloy/cache/toolchain.cmake` whenever the
lockfile changes (stamp-keyed on `lockfile_sha + alloy_cli_version`,
mirrors the codegen stamp pattern).  Contents:

```cmake
# AUTO-GENERATED by alloy-cli — do not edit.
# Stamp: lockfile_sha=abc... alloy_cli=0.1.0
set(CMAKE_C_COMPILER   "/Users/foo/.local/share/alloy/tools/by-name/arm-none-eabi-gcc/14.2/bin/arm-none-eabi-gcc")
set(CMAKE_CXX_COMPILER "/Users/foo/.local/share/alloy/tools/by-name/arm-none-eabi-gcc/14.2/bin/arm-none-eabi-g++")
set(CMAKE_ASM_COMPILER "/Users/foo/.local/share/alloy/tools/by-name/arm-none-eabi-gcc/14.2/bin/arm-none-eabi-gcc")
set(CMAKE_AR           "/Users/foo/.local/share/alloy/tools/by-name/arm-none-eabi-gcc/14.2/bin/arm-none-eabi-ar")
# … etc.
```

CMake then resolves the rest (linker, objcopy, …) relative to the
chosen compiler.  No CMake module rewrite is needed; the toolchain
file is the canonical CMake escape hatch.

When no project lockfile exists, `core.build.run` skips the
toolchain file generation and CMake falls back to today's PATH
resolution — so the behaviour change is fully opt-in via the
presence of `toolchain.lock`.

### D6: Source adapters are a closed set, dispatched by `source` prefix

Wave 1 already encoded the `source` enum:
`xpack | github:<owner>/<repo> | probe-rs-installer | espressif | vendor`.
Wave 2 maps the first four prefixes to adapter classes:

| Prefix | Adapter | Pin file |
|---|---|---|
| `xpack` | `XpackAdapter` | `data/sources/xpack.json` |
| `github:` | `GithubAdapter` | `data/sources/github.json` |
| `probe-rs-installer` | `ProbeRsAdapter` | `data/sources/probe-rs.json` |
| `espressif` | `EspressifAdapter` | `data/sources/espressif.json` |
| `vendor` | (none — Wave 1 renderer owns it) | — |

Each adapter exposes the same shape:

```python
class Source(Protocol):
    def resolve(self, tool: ToolRequirement, host: HostTriple) -> SourceArtifact: ...
```

Adding a new source (e.g. `microchip-cube` for SAM-BA tools) is
a new adapter + a new JSON file; the dispatcher in
`tool_sources.adapter_for(...)` grows by one elif.

### D7: Trust boundaries are explicit

Three things need security review:

1. **The pin files (`data/sources/*.json`).**  These are reviewed
   like any other change at PR time.  CI verifies their schema.
   `scripts/refresh_source_pins.py` only ever writes to disk; it
   never opens a PR — a maintainer must manually open the PR.
2. **The download stream.**  Streaming SHA256 verification (D3
   step 3) makes a tampered artefact undetectable-but-rejected
   before any byte is finalised.  TLS via stdlib `urllib.request`
   defends against MITM; `urllib` honours system trust roots.
3. **The extraction.**  We use Python 3.12+ `tarfile.data_filter`
   (path traversal mitigation) when available.  Older Pythons get
   a pre-extraction sanitisation pass that rejects archives whose
   members try to escape the destination.

We explicitly do NOT trust:

- The local user's PATH (compilers come from the store).
- The local user's TLS proxy (we don't disable verification).
- Upstream URLs we haven't pinned (every URL crosses
  `data/sources/*.json` first).

### D8: Cross-platform host triple resolution

`core.tool_sources.host_triple()` returns a tuple `(os, arch)`:

| Python `platform.system()` | os |
|---|---|
| `Darwin` | `macos` |
| `Linux` | `linux` |
| `Windows` | `windows` |

| Python `platform.machine()` | arch |
|---|---|
| `x86_64`, `AMD64` | `x86_64` |
| `arm64`, `aarch64`, `arm64e` | `arm64` |

Other combinations raise `family-toolchain-installer-unsupported-host`
with the actual triple in the message.  The pin files declare which
hosts they support per tool; missing host = same typed error.

**Alternatives considered:**

- *Triple format like `aarch64-apple-darwin`.*  Rejected: extra
  precision we don't yet need (we don't ship distro-specific
  binaries; xpack already abstracts glibc differences).
- *Auto-translate aliases like `amd64` → `x86_64` lazily in
  adapters.*  Rejected: centralising the alias table in
  `host_triple()` keeps adapters dumb.

### D9: Network seam is `Downloader` Protocol, not raw `urllib`

`core.tool_sources.Downloader` is a Protocol with one method:

```python
def fetch(self, artifact: SourceArtifact, dest: Path, *, on_progress: Callable[[int, int], None] | None = None) -> Path
```

Production: `_RealDownloader` uses `urllib.request.urlopen` with a
custom `Request` carrying alloy-cli's user-agent string (so server
logs are honest about who's hitting them).  Tests inject a
`FakeDownloader` that copies a fixture tarball into `dest` so no
network call happens in CI.

Mirrors the `CommandRunner` protocol pattern from Wave 1; shares the
same testability story.

### D10: Linux udev rules emit, never apply

When a tool with `udev_required: true` installs on Linux, the
manager writes the rules to `<base>/alloy/udev/<tool>.rules` and
prints:

```
✓ Wrote udev rules to ~/.local/share/alloy/udev/probe-rs.rules
  Run this once to enable non-root probe access:
    sudo cp ~/.local/share/alloy/udev/probe-rs.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
```

Sudo is **never** invoked silently.  The rules content comes from
the source pin file (e.g. probe-rs ships its rules as a release
asset; we pin and bundle them like any other artefact).

## Risks / Trade-offs

- **[Risk]** Pinned URLs rot when upstream restructures their
  release infrastructure.
  → **Mitigation**: `scripts/check_family_doc_links.py` (Wave 1)
  is extended to also HEAD every `data/sources/*.json` URL.
  `scripts/refresh_source_pins.py` walks upstream feeds and
  regenerates the JSONs.  Both run on a periodic CI schedule;
  failures are warnings, not blockers, on per-PR CI.

- **[Risk]** Disk usage spirals when users hop between many
  families / versions.
  → **Mitigation**: `alloy toolchain prune` does GC against the
  union of every known project's `.alloy/toolchain.lock`.  The
  doctor JSON contract grows a `store_size_bytes` field so users
  can monitor.  We document the prune verb prominently in
  `docs/TOOLCHAIN_INSTALLER.md`.

- **[Risk]** Concurrent installs from different terminals.
  → **Mitigation**: advisory file lock on `<base>/alloy/tools/.lock`.
  When held, the second invocation surfaces
  `family-toolchain-installer-locked` so the user knows another
  process owns the lock.  POSIX uses `fcntl.flock`; Windows uses
  `msvcrt.locking`.

- **[Risk]** Path-traversal exploit via a crafted tarball.
  → **Mitigation**: `tarfile.data_filter` on Python 3.12+; explicit
  member-by-member sanitisation on older Pythons.  CI tests pin
  this with a pathological fixture.

- **[Risk]** A user's enterprise TLS proxy intercepts and
  re-signs the download with a private CA.  The SHA256 still
  matches (the proxy didn't tamper, just re-signed) but the user
  experiences confusing TLS errors.
  → **Mitigation**: stdlib `ssl` honours `SSL_CERT_FILE` /
  `SSL_CERT_DIR`; the doc explicitly mentions this for
  enterprise users.  We do NOT disable verification.

- **[Risk]** The store grows beyond what the user expected.
  → **Mitigation**: `alloy toolchain install --dry-run` always
  prints the planned total size.  `alloy toolchain list --json`
  reports `store_size_bytes`.  `alloy doctor` JSON also
  surfaces total store size.

- **[Risk]** `os.rename` across filesystems fails (e.g.,
  `/tmp` is `tmpfs`, `~/.local/share` is `ext4`).
  → **Mitigation**: the `.tmp/` staging area lives INSIDE the
  store directory, so the rename is always intra-filesystem.

- **[Risk]** Windows lacks symlinks for unprivileged users; the
  `by-name/<tool>/<version>` shortcut needs a different
  mechanism.
  → **Mitigation**: emit `_pointer.txt` text files containing
  the SHA on Windows.  The resolver reads the pointer file
  when symlinks aren't available.  Tests exercise both paths.

- **[Trade-off]** Wave 2 cannot install vendor tools, so users
  on STM32 with locked RDP still need to leave alloy-cli to
  download STM32CubeProgrammer.
  → **Accepted**: legal constraint.  Wave 1's renderer already
  surfaces the doc URL; Wave 4 will run the user's installed
  copy when present (`alloy recover`).

- **[Trade-off]** No retry policy beyond a single backoff
  attempt for transient HTTP errors.
  → **Accepted**: a download manager is out of scope.  CI users
  can wrap the call in their own retry logic if they need to.

## Migration Plan

This is purely additive at the user surface.  No deprecations, no
breaking changes to `alloy.toml`, no behavioural change for
projects without a `.alloy/toolchain.lock`.

Roll-out order (one PR per task block in `tasks.md`):

1. Schema + first source pins (xpack arm-gcc + cmake + ninja for
   the five host triples).  Lands without code changes; tests
   validate every JSON file.
2. `core.tool_sources` adapters + Downloader protocol + fakes.
   No external surface change yet; tests cover every adapter +
   the dispatcher.
3. `core.toolchain_manager` (store + lockfile + flock + atomic
   install + GC).  Still no CLI surface change.
4. `commands/toolchain.py` — the five `alloy toolchain` verbs.
5. CMake toolchain file generation in `core.build.run`.
6. flash + debug binary resolution via the store.
7. MCP read-only tools.
8. Docs + cookbook + cheatsheet regeneration.
9. Validation + CHANGELOG entry.

Rollback per block: each is independently revertable.  The CMake
toolchain file generation lands BEHIND the lockfile presence
gate, so reverting it doesn't break any project that hasn't run
`alloy toolchain install` yet.

## Open Questions

- **Q1**: Should the toolchain lockfile sit in `.alloy/` or at the
  project root next to `alloy.toml`?  Today's `.alloy/version.lock`
  is in `.alloy/`; users sometimes commit it.  toolchain.lock has
  the same property (project-bound, ~10 KB).
  → *Proposed answer*: `.alloy/toolchain.lock`.  Co-locating with
  `version.lock` keeps the "everything alloy" tree together and
  avoids tempting hand-edits at the project root.  We document
  that committing it is recommended for reproducible builds.

- **Q2**: When `alloy toolchain install` finds a tool whose
  desired version is in our pin file but a DIFFERENT version is
  already installed locally, do we install the desired one
  alongside (parallel versions) or upgrade in place?
  → *Proposed answer*: install alongside.  Two projects on the
  same machine can pin different versions; `prune` reaps the
  losers.  This is the cargo / rustup / pyenv pattern.

- **Q3**: Should `alloy toolchain shell` source the user's
  bash/zsh init files in the spawned subshell?
  → *Proposed answer*: spawn `$SHELL -i` on POSIX
  (interactive shell, sources rc files), `cmd.exe /K` on
  Windows.  PATH is augmented BEFORE init so user customisations
  can see our tools.

- **Q4**: How does the lockfile interact with `alloy update`
  (which today bumps alloy / alloy-codegen / alloy-devices-yml /
  alloy-cli)?
  → *Proposed answer*: out of scope this wave.  `alloy update`
  stays focused on the alloy ecosystem; toolchain pins move via
  `alloy toolchain use <tool>@<version>`.  Wave 5 (later) can
  unify if users ask for it.

- **Q5**: Should the udev rules be applied automatically when the
  user runs `alloy toolchain install --apply-udev`?
  → *Deferred*: writing under `/etc/udev/rules.d/` requires sudo
  privileges; running sudo from inside a CLI tool is a footgun
  (terminal hijack, shell-injection vectors).  The
  copy-instruction approach keeps the privileged step explicit.
  Wave 4's recovery work may revisit this with a `--with-sudo`
  hook that prompts for a password explicitly.
