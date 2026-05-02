"""Core operations of alloy-cli.

Pure-functional layer that the three façades (CLI, TUI, MCP) all
call into.  No I/O at module load.  No mutable global state.
Every function takes explicit arguments and returns explicit
results.
"""
