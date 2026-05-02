# Tasks — add-mcp-server

## Phase 1: Server scaffold

- [x] 1.1 ``mcp>=0.10`` is already declared under
      ``[project.optional-dependencies] mcp`` in ``pyproject.toml``.
- [x] 1.2 ``src/alloy_cli/mcp/server.py`` ships a stdio JSON-RPC
      fallback (``serve_stdio_fallback``) that round-trips the
      registry without requiring the SDK; importing the SDK lands
      automatically once the user installs ``alloy-cli[mcp]``.
- [x] 1.3 ``alloy mcp serve`` Click command exposes ``--transport
      {stdio,http,sse}`` and ``--cwd``.  Today only stdio is
      wired; HTTP / SSE require the SDK and surface a clean error.
- [x] 1.4 Tool registration via ``Tool`` + ``ToolRegistry``.
      Handlers are plain Python functions; descriptions live in
      docstrings; parameter schemas are stored in
      ``_PARAM_SCHEMA`` so the SDK adapter can map them later.

## Phase 2: Read-only tools

- [x] 2.1 ``list_boards(query?)`` → ``core.search.search_boards``.
- [x] 2.2 ``list_devices(query?, vendor?, family?, include_bulk?)``
      → ``core.search.search_devices``.
- [x] 2.3 ``query_device_ir(vendor, family, device,
      peripheral_class?)`` → narrow IR view.
- [x] 2.4 ``suggest_pins(vendor, family, device, peripheral,
      signal)`` → ``core.ir.valid_pins_for``.
- [x] 2.5 ``suggest_dma`` is **deferred** — alloy-devices-yml
      doesn't yet ship the per-peripheral request_value table the
      function would key on.  The DMA suggestion logic in
      ``core.suggestions.suggest_dma`` already works for
      same-device peripheral wiring; surfacing it via MCP lands
      with the codegen DMA enrichment.
- [x] 2.6 ``read_alloy_toml()`` → ``core.project.read``.
- [x] 2.7 ``list_recent_events(limit?)`` → tail of
      ``.alloy/cache/events.jsonl``.

## Phase 3: Mutating tools (transactional)

- [x] 3.1 ``preview_diff(kind, name, payload?)`` previews the
      peripheral add without writing files; caches the resulting
      diff under a ``diff_id`` for a 5-minute TTL.
- [x] 3.2 ``add_uart`` / ``add_gpio`` / ``add_spi`` / ``add_i2c``
      delegate to ``core.peripherals.add_*`` and return
      ``{diff_id, diff_text, validation_summary}``.
- [x] 3.3 ``apply_diff(diff_id)`` looks up the cached diff and
      writes each ``FilePatch`` atomically.  Stale ids surface
      as ``StaleDiffError``; consumed ids vanish from the cache.
- [x] 3.4 ``set_clock_profile(profile)`` caches an alloy.toml
      clocks-only diff.
- [x] 3.5 ``build(profile?)`` runs ``core.build.run`` through the
      registry's runner (FakeRunner-friendly in tests, real
      subprocess in production).
- [x] 3.6 ``flash(elf, probe_kind?, target?)`` runs
      ``core.flash.run``.

## Phase 4: Error model

- [x] 4.1 ``ToolError`` is the dataclass returned to MCP callers;
      ``ToolRegistry.call`` re-wraps the ``BoardNotFoundError /
      DeviceNotFoundError / PinInvalidError / AlloyCliError``
      hierarchy so each carries an ``error_type`` discriminator.
- [x] 4.2 The structured error dict is included in the JSON-RPC
      ``error`` payload so LLMs can branch on the type.

## Phase 5: Tool descriptions

- [x] 5.1 Every tool has a docstring stating purpose,
      preconditions, and side effects.
- [x] 5.2 ``test_every_tool_has_non_empty_description`` is the
      regression for that contract.

## Phase 6: Tests

- [x] 6.1 In-process registry harness covers every tool —
      ``test_default_registry_lists_required_tools`` enforces the
      spec's discovery contract.
- [x] 6.2 End-to-end stdio test: ``alloy mcp serve --cwd <tmp>``
      is spawned via ``subprocess.run``, fed a ``call_tool``
      request, and produces ``{"result": ...}`` for
      ``read_alloy_toml``.
- [x] 6.3 Hallucination-defence test:
      ``test_add_gpio_with_invalid_pin_returns_validation_summary``
      asserts the response has ``has_errors=True`` and an
      ``unknown-pin`` diagnostic with suggestions, with
      ``diff_id`` cleared.

## Phase 7: Spec + final checks

- [x] 7.1 Spec deltas in ``specs/mcp-surface/spec.md``.
- [x] 7.2 ``openspec validate add-mcp-server --strict`` passes.
- [x] 7.3 README "AI integration" section linking to the
      ``recommend-opencode-host`` recipe lands with that proposal.
