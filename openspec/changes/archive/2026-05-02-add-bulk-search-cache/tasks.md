# Tasks — add-bulk-search-cache

## Phase 1: Cache module

- [x] 1.1 `core.search._BulkCache` dataclass with `read`,
      `write`, `_prune`, and `clear` methods, all keyed on a
      SHA string.
- [x] 1.2 SHA discovery via `git -C data/devices rev-parse
      HEAD` (subprocess-based, 2 s timeout); falls back to
      `None` when git is missing or the directory isn't a
      repo, which disables the cache.
- [x] 1.3 Atomic write: temp file + `os.replace` so a partial
      flush never corrupts the cache.

## Phase 2: Integration

- [x] 2.1 `core.search._bulk_summaries_from_index()` consults
      `_BulkCache` before reading the YAML.
- [x] 2.2 Cache hit returns deserialised
      `tuple[DeviceSummary, ...]`; cache miss falls back to
      the existing parser, then writes the cache.
- [x] 2.3 `core.search.reset_caches()` clears both the LRU
      and the on-disk cache directory.

## Phase 3: Eviction

- [x] 3.1 Each `write` runs `_prune()` which keeps the 3
      most-recent SHAs by mtime; older entries are deleted.

## Phase 4: Tests

- [x] 4.1 Unit tests cover read / miss / round-trip / prune
      / unreadable JSON / invalid schema / atomic write.
- [x] 4.2 Cache-hit regression: a synthetic bulk index drives
      two `_bulk_summaries_from_index` calls; the YAML
      `safe_load` runs exactly once (the second call hits the
      cache).
- [x] 4.3 SHA invalidation regression: removing the data
      devices submodule yields `_submodule_sha() == None` and
      the cache is silently disabled.
- [x] 4.4 `reset_caches()` clears both the LRU and the
      on-disk directory.

## Phase 5: Spec + final checks

- [x] 5.1 Spec deltas in `specs/data-integration/spec.md`.
- [x] 5.2 `openspec validate add-bulk-search-cache --strict`
      passes.
