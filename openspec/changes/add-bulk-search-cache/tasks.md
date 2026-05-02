# Tasks — add-bulk-search-cache

## Phase 1: Cache module

- [ ] 1.1 `core.search._BulkCache` dataclass with `read` /
      `write` / `prune` methods, all keyed on a SHA string.
- [ ] 1.2 SHA discovery via `git -C data/devices rev-parse
      HEAD`; falls back to `"unknown"` when git is missing
      (which disables the cache).
- [ ] 1.3 Atomic write: temp file + `os.replace` so a partial
      flush never corrupts the cache.

## Phase 2: Integration

- [ ] 2.1 `core.search.search_devices(admitted="all", ...)`
      consults `_BulkCache` before reading the YAML.
- [ ] 2.2 Cache hit returns deserialised
      `tuple[DeviceSummary, ...]`; cache miss falls back to
      the existing parser, then writes the cache.
- [ ] 2.3 `core.search.reset_caches()` removes the directory
      contents in addition to clearing the LRU.

## Phase 3: Eviction

- [ ] 3.1 Each `write` runs a small pruner that keeps the 3
      most-recent SHAs by mtime.

## Phase 4: Tests

- [ ] 4.1 Unit tests for cache hit / miss / prune flows.
- [ ] 4.2 Benchmark: warm-cache `search_devices(admitted=
      "all")` lands in under 100 ms on the bundled dataset.
- [ ] 4.3 Regression: invalidating SHA (mocked) forces a
      re-parse.
- [ ] 4.4 `reset_caches()` clears both layers.

## Phase 5: Spec + final checks

- [ ] 5.1 Spec deltas in `specs/data-integration/spec.md`.
- [ ] 5.2 `openspec validate add-bulk-search-cache --strict`
      passes.
