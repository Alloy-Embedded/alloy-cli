# Contributing

Short version.

## Workflow

1. **Find the relevant OpenSpec proposal.**  Every change goes
   through `openspec/changes/<id>/`.  If your change isn't covered
   by an active proposal, write one.

2. **Read `docs/ARCHITECTURE.md` + `docs/TUI_DESIGN.md`.**  The
   non-negotiable principles live there.

3. **Match the existing layering.**  `core/` is pure; `cli/` /
   `tui/` / `mcp/` are thin façades over `core/`.  Don't put logic
   in a façade.

4. **Snapshot tests for every TUI screen.**  Use
   `pytest-textual-snapshot`.  CI enforces.

5. **Diff before apply, every operation.**  No silent file mutation.

6. **CLI parity.**  If you add a TUI knob, add the matching
   `--flag`.  CI bots don't have terminals.

7. **`pyright --strict` clean.**  Every `core/` module typed.

## Quick start

```bash
git clone https://github.com/Alloy-Embedded/alloy-cli
cd alloy-cli
git submodule update --init     # fetches alloy-devices-yml

uv venv && source .venv/bin/activate
uv pip install -e ".[dev,mcp]"

pytest -q                       # unit + snapshot tests
ruff check .
pyright src/alloy_cli
```

## Where to start

| Want to | Start in |
|---|---|
| Add a new peripheral kind | `src/alloy_cli/core/peripherals.py` |
| Change a TUI screen | `src/alloy_cli/tui/screens/` |
| Add a new MCP tool | `src/alloy_cli/mcp/tools.py` |
| Document an architecture decision | `docs/ARCHITECTURE.md` |
| Propose a feature | `openspec/changes/<id>/proposal.md` |

## Style

- Python 3.11+.
- `ruff` + `pyright --strict`.  No `# type: ignore` without a
  comment explaining why.
- Module docstrings explain purpose.  Function docstrings explain
  contract (preconditions, postconditions, invariants).
- No emojis in code.  Glyphs in TUI are deliberate.

## License

Dual MIT / Apache-2.0.  Contributors implicitly license under both.
