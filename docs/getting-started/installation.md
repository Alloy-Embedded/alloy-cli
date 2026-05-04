# Installation

## System requirements

- **Python 3.11+** (3.13 recommended).
- **macOS / Linux / Windows** — alloy-cli is platform-agnostic;
  the toolchain installer handles the OS-specific bits.
- **An ST-Link / J-Link / CMSIS-DAP / picoprobe** (only when you
  flash hardware — alloy works without one).

You do **not** need to pre-install `arm-none-eabi-gcc`, `cmake`,
`ninja`, or `probe-rs`.  The post-scaffold prompt pulls them
into a per-user content-addressed store and pins each by SHA256
in `.alloy/toolchain.lock`.

## Install alloy-cli

=== ":material-package-variant-closed: pip"

    ```bash
    pip install alloy-cli
    ```

=== ":material-flash: pipx (isolated)"

    ```bash
    pipx install alloy-cli
    ```

=== ":material-cog: From source"

    ```bash
    git clone https://github.com/Alloy-Embedded/alloy-cli.git
    cd alloy-cli
    pip install -e '.[dev]'
    ```

Verify:

```bash
alloy --version
```

## Optional extras

`alloy-cli` ships with three optional dependency groups:

| Extra | Install | What you get |
|---|---|---|
| `mcp` | `pip install 'alloy-cli[mcp]'` | The official Anthropic MCP SDK — required for the `alloy mcp serve` stdio transport. |
| `dev` | `pip install -e '.[dev]'` | Test runner, ruff, pyright, mypy, pytest plugins. |
| `docs` | `pip install -e '.[docs]'` | MkDocs Material + plugins (only needed to build the doc site locally). |

If anything is missing on your system, `alloy doctor --fix`
auto-fixes the optional `mcp` Python extra and any required
non-vendor binary tools the project's family declares.

## What's next?

1. **[Quickstart](../QUICKSTART.md)** — the canonical 5-minute
   walkthrough from `pip install` to a flashed Nucleo.
2. **[Your first project](your-first-project.md)** — a deeper
   walkthrough that adds peripherals, walks the IR validation,
   and explains the toolchain lockfile.
3. **[Toolchain onboarding](../TOOLCHAIN_ONBOARDING.md)** — the
   reference for every entry point that installs the per-family
   toolchain.

## Troubleshooting

If `alloy --version` fails:

- Confirm Python 3.11+: `python --version`.
- Confirm the `pip` you used matches that Python:
  `pip --version`.
- For pipx, confirm `pipx ensurepath` ran successfully.

If you see an error_type like `family-toolchain-installer-...`
during the post-scaffold prompt, head straight to the
[Error cookbook](../ERROR_COOKBOOK.md) — every typed error has a
recovery checklist.
