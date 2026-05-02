## ADDED Requirements

### Requirement: Bulk device search SHALL cache results keyed on the alloy-devices-yml submodule SHA

`core.search.search_devices(... admitted="all")` SHALL consult a
disk cache under `.alloy/cache/bulk_search/<sha>.json` before
parsing `data/devices/bulk-admitted/index.yml`.  The cache key
SHALL be the SHA returned by `git -C data/devices rev-parse
HEAD`; cache miss or git failure SHALL fall through to the
existing YAML parser and SHALL repopulate the cache.  Cache
writes SHALL be atomic (temp file + rename).  The cache
directory SHALL retain at most three keys; older entries SHALL
be pruned at write time.

#### Scenario: warm cache returns under 100 ms

- **WHEN** `core.search.search_devices(admitted="all")` runs a
  second time without the submodule SHA having changed
- **THEN** the call SHALL return in under 100 ms on the
  bundled fixture
- **AND** the YAML parser SHALL NOT be invoked

#### Scenario: submodule SHA bump invalidates the cache automatically

- **WHEN** the user runs `alloy update` (or otherwise moves
  the submodule HEAD)
- **AND** subsequently runs `alloy devices --include-bulk`
- **THEN** the lookup SHALL miss the cache (the SHA key
  changed)
- **AND** SHALL re-parse the YAML and write a new cache file
- **AND** the prior cache file SHALL be pruned once more than
  three keys exist

#### Scenario: reset_caches() clears both layers

- **WHEN** the test suite calls
  `core.search.reset_caches()`
- **THEN** the in-process LRU SHALL be cleared
- **AND** every file under `.alloy/cache/bulk_search/` SHALL
  be removed
