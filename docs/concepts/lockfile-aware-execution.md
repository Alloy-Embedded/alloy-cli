# Lockfile-aware execution

Every alloy-cli project that has installed its toolchain has a
`.alloy/toolchain.lock` file.  The lockfile pins each binary by
**SHA256** of the upstream archive.  Build / flash / debug
commands resolve absolute paths from the lockfile, never from
`$PATH`.

## The shape

```toml
schema_version = "1.0.0"

[[tools]]
tool = "arm-none-eabi-gcc"
version = "14.2.1-1.1"
sha256  = "9d18bbe3ebec46540...5b2"
source  = "xpack"

[[tools]]
tool = "cmake"
version = "3.31.2"
sha256  = "..."
source  = "xpack"

[[tools]]
tool = "probe-rs"
version = "0.27.0"
sha256  = "..."
source  = "probe-rs-installer"

# … etc.
```

Every entry pins the exact archive that was downloaded.  Lookups
go through the **content-addressed store** at
`platformdirs.user_data_dir("alloy")/tools/store/<sha256>/`.

## Why path resolution from the lockfile?

Three problems with `$PATH`:

1. **Reproducibility** — `cmake --version` differs across
   contributors; the lockfile pins one version per project.
2. **Multiple toolchains on one machine** — you might have arm-
   gcc 13.x for one project and 14.x for another; PATH-based
   resolution can't keep them straight.
3. **Vendor tools** — STM32CubeProgrammer lives in a vendor-
   specific install path; resolution-by-PATH would force every
   contributor to set the same env.

The lockfile sidesteps all three: each project pins its toolset,
each binary resolves to a specific absolute path, vendor tools
surface as info rows pointing at their install_doc URL.

## Where the resolution happens

```python
from alloy_cli.core import lockfile_toolchain as _lf

lock = _lf.read_optional(Path(".alloy/toolchain.lock"))
arm_gcc = _lf.resolve_binary(lock, "arm-none-eabi-gcc")
# → PosixPath("~/Library/Application Support/alloy/tools/by-name/...")
```

`alloy build`, `alloy flash`, `alloy debug` all call
`resolve_binary` for every tool they need.  When the lockfile
doesn't exist (fresh checkout), they fall back to PATH and
print a "run `alloy toolchain install` to pin the version" hint.

## The store layout

```
~/Library/Application Support/alloy/tools/
├── store/
│   ├── <sha256-of-arm-gcc-archive>/
│   │   └── (extracted contents)
│   └── <sha256-of-cmake-archive>/
│       └── (extracted contents)
├── by-name/
│   └── arm-none-eabi-gcc/
│       └── 14.2.1-1.1 → ../../store/<sha256>/  (symlink)
└── manifest.json
```

The `by-name/` tree gives a stable lookup path independent of the
SHA; the `store/` tree is the ground-truth content addressing.

## Cross-references

- [`docs/TOOLCHAIN_INSTALLER.md`](../TOOLCHAIN_INSTALLER.md) —
  Wave 2's pin file format + atomic install pipeline.
- [Toolchain orchestrator](toolchain-orchestrator.md) — what
  populates the lockfile.
- `src/alloy_cli/core/lockfile_toolchain.py` — the lockfile
  reader / writer.
