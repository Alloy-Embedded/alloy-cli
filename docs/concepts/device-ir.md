# Device IR

The **device IR** is alloy-cli's typed, schema-locked
representation of every chip, board, and peripheral it supports.
It's the single source of truth that pin pickers, clock-tree
visualisers, peripheral validators, and the codegen pipeline all
read from.

## Why a typed IR?

Vendor SDKs ship XML / JSON / proprietary blobs that vary by chip
family.  CubeMX has its own database; pic16's headers carry a
different shape; nRF SDKs split definitions across three
namespaces.  Without a normalisation layer, every alloy-cli
feature would have to reimplement "find a UART RX pin on
USART2".

The IR collapses that to **one schema**:

```python
device.peripherals["USART2"].signals["RX"].candidates
# → ('PA3', 'PD6', ...) — IR tells you which pins this signal can land on
```

Every read goes through `alloy_cli.core.ir.load_device(vendor,
family, device)`.  The loader consumes vendor data + a
hand-curated overlay (`alloy-devices-yml`, the data submodule),
validates against a JSON Schema, and returns a frozen Python
dataclass tree.

## Where it comes from

- **Source data**: vendor IP-XACT / SVD / atmel-pack files,
  pulled into `alloy-devices-yml` as canonical YAML.
- **Schema**: `schema/device_ir_v1.json` (Draft 2020-12).
  Anything that doesn't validate is rejected at load time.
- **Loader**: `alloy_cli.core.ir.load_device` — pure function,
  no I/O at module load, lru-cached on `(vendor, family,
  device)`.
- **Test seam**: `FakeIR` in tests; production never reaches
  vendor data files.

## How features use it

| Feature | What it asks the IR |
|---|---|
| `alloy add uart` | "Which pins can carry USART2 RX?" |
| `alloy doctor` | "Does this clock profile boot the chip?" |
| TUI pin picker | "Highlight every PA3 alternative function" |
| MCP `suggest_pins` | "Return the three best matches for 'I2C SCL'" |

If a tool wants to ask the chip a question, it goes through the
IR.  No vendor SDK in the call graph.

## Typed errors

Bad combinations fail with **structured diagnostics** at config
time:

```text
PinInvalidError: PA2 cannot carry USART1.RX on stm32g071rb
  candidates: PA10, PB7
  → see ERROR_COOKBOOK.md#PinInvalidError
```

The error_type is stable; LLM agents branch on it and call
`suggest_pins` to recover.

## Cross-references

- [`docs/PROJECT_FORMAT.md`](../PROJECT_FORMAT.md) — how
  `alloy.toml` references the IR.
- [`docs/DATA_SOURCES.md`](../DATA_SOURCES.md) — where the IR's
  upstream data comes from.
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — full architecture
  with the IR's place in the pipeline.
