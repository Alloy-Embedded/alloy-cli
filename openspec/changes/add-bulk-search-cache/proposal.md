# Cache Bulk-Admitted Device Search by Submodule SHA

## Why

`alloy devices --include-bulk` (and the equivalent MCP tool)
parses `data/devices/bulk-admitted/index.yml` from disk on every
invocation.  That YAML is ~7 MB and the pure-Python parse takes
~7 s on a warm cache, ~12 s cold.  Users hit it on every search;
agents hit it once per turn.

The catalog only changes when the alloy-devices-yml submodule
SHA changes.  A keyed cache under `.alloy/cache/bulk_search/<sha>.json`
takes the cost from "noticeable lag" to "<100 ms" on the second
call — and the cache invalidates automatically when the
submodule moves.

## What Changes

### Cache module

- New `core.search._BulkCache` class:
  - `key_for_repo() -> str` returns the active submodule SHA
    (read once via `git -C data/devices rev-parse HEAD`).
  - `read(key) -> list[DeviceSummary] | None` deserialises a
    cached result; missing keys return `None`.
  - `write(key, summaries) -> None` writes a single JSON file
    `(.alloy/cache/bulk_search/<key>.json)` with atomic
    rename.

### Hot path

- `core.search.search_devices(... admitted="all")` consults the
  cache first; on a miss it parses the YAML, populates the
  cache, and returns the result.
- `core.search.reset_caches()` clears both the in-process LRU
  *and* the on-disk cache directory (CI / tests need this).

### Eviction

- The cache directory keeps the 3 most-recent SHAs (one per
  unique submodule head).  Older entries are pruned at write
  time.  Total disk footprint capped at ~30 MB.

## Impact

- `alloy devices --include-bulk` second invocation drops from
  ~7 s to <100 ms.
- MCP `list_devices(include_bulk=true)` becomes safe to call
  every turn without the agent perceiving lag.
- Cache invalidates automatically when the user runs `alloy
  update` (which moves the submodule SHA).

## What this DOES NOT do

- Does not introduce a server-side cache (the data is local to
  the checkout).
- Does not deduplicate / dedupe devices across vendors.
- Does not pre-warm the cache; first invocation still pays the
  parse cost.  A `alloy devices --warm-cache` subcommand could
  follow.
