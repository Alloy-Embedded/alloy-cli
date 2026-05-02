# TUI Design

> The screens that decide whether `alloy-cli` is a footnote or the
> default way embedded firmware gets configured.

This document is the design contract for the Terminal UI.  It exists
**before any code is written** so every TUI proposal under
`openspec/changes/add-tui-*/` references this as the source of truth.

We're benchmarking against:

- **STM32 CubeMX** (graphical, ST-only, the gold standard for pin
  pickers and clock trees in 2026)
- **MCUXpresso** (graphical, NXP-only)
- **Renesas e²studio** (graphical, Renesas-only)
- **PlatformIO Home** (electron, multi-vendor, no pin picker)
- **Modm/lbuild** (CLI-only, no visualisation)

We're not benchmarking against IDEs (VS Code, CLion).  Those are
**editors**.  We're a **configurator**.

## Design principles

These are non-negotiable.  Every screen, widget, and interaction
follows them.

### 1. Information density beats whitespace

Embedded developers run `alloy-cli` on 80×24 SSH sessions, on
1080p monitors with split panes, on 4K displays.  We optimise for
**information per cell** without scrolling, not for the modal-spaced
"clean" look web apps prefer.  CubeMX's pin picker shows ~140 pins
with ~5 properties each on a single screen.  We match that density.

### 2. Color is data, not decoration

| Color | Meaning |
|---|---|
| dim grey | unavailable / disabled / inapplicable |
| white | neutral / unselected available |
| cyan | currently focused |
| green | valid / assigned / OK |
| yellow | warning / suggestion |
| red | error / conflict |
| magenta | candidate / suggested |
| bright bg | currently being modified |

Never use color for branding.  Always pair color with a glyph for
color-blind / `NO_COLOR=1` accessibility.  Defined glyphs:

```
✓ ok / valid / assigned        ✗ error / conflict
◉ selected / focused           ○ unselected available
◆ candidate / suggested        ► already assigned (read-only)
▣ reserved (debug, power, …)   ◌ unbonded / not in package
↑↓ navigate                    ⇥ tab between fields
```

### 3. Always show "what next"

Every screen has a status bar at the bottom listing the relevant
keybindings.  Bindings are **contextual** — different per focused
widget.

Example:
```
↑↓ navigate · / search · Tab filter · Enter select · q quit
```

When focus is on a different widget:
```
←→ adjust · Space toggle · Ctrl+S apply · Esc cancel
```

### 4. Don't ask if we can infer

If there is exactly one valid choice, pre-select it.  If there's a
clearly best choice (e.g., the only free DMA channel on the requested
direction), pre-select that and dim the others.  The user can always
override.

### 5. Diff before apply, every time

No screen mutates the project on the user's behalf without showing a
unified diff first.  `Ctrl+D` opens the diff modal.  `Ctrl+S` applies.
Defaults are: TUI = `Ctrl+D` first, `Ctrl+S` to apply.  CLI = `--apply`
flag required (else dry-run).

### 6. Searchable everything

`/` enters fuzzy filter mode in any list.  `Ctrl+P` opens the global
command palette.  No menu deeper than 2 levels.

### 7. Degrades gracefully

- **`NO_COLOR=1`**: glyphs replace colour, layout unchanged.
- **plain xterm (no truecolor, 16 colors)**: dim/bright variants
  collapse to 16-color palette without losing meaning.
- **80-column terminal**: panels stack vertically, less density per
  panel but no horizontal scroll.
- **Screen reader**: every glyph + colour pair has an aria-label
  (Textual supports this).

### 8. Performance is a UX feature

| Action | Budget |
|---|---|
| Initial paint after `alloy ui` | < 300 ms |
| Switch screens (Tab between dashboard + add) | < 50 ms |
| Pin search filter | < 20 ms keystroke-to-paint |
| Apply diff (write files) | < 200 ms |
| Live build log throughput | 1 000+ lines/s without dropping |

## The screen catalogue

12 screens.  Each documented here with its purpose, layout, data
requirements, and interactions.

### Index

| # | Screen | Trigger | Phase |
|---|---|---|---|
| 1 | **Dashboard** | `alloy` (in project), `alloy ui` | 3 |
| 2 | **Board picker** | `alloy new`, `alloy boards` | 3 |
| 3 | **Peripheral assignment** | `alloy add <kind>` | 3 |
| 4 | **Clock tree** | `alloy clocks` | 3 |
| 5 | **DMA matrix** | `alloy dma` | 5 |
| 6 | **Memory map** | `alloy memory` | 5 |
| 7 | **Build log** | `alloy build` (live) | 3 |
| 8 | **Flash progress** | `alloy flash` (live) | 3 |
| 9 | **Diff modal** | global, before any apply | 3 |
| 10 | **Command palette** | `Ctrl+P` global | 3 |
| 11 | **Doctor** | `alloy doctor` | 5 |
| 12 | **Onboarding wizard** | first run, no `alloy.toml` | 3 |

---

## Screen 1 — Dashboard

The **home screen** the user lands on inside a configured project.
Single source of truth for "what is my project right now?"

### Layout

```
╭───────────────────── alloy · my-firmware ────────────────────────────╮
│  Board       nucleo_g071rb · STM32G071RB · Cortex-M0+                 │
│  Toolchain   arm-none-eabi-gcc 13.2.0 · ✓                             │
│  Probe       J-Link via probe-rs · ✓                                  │
│  Clock       64 MHz from PLL  (default_pll_64mhz)                     │
│  alloy-cli   0.5.0      alloy 0.7.3      codegen 0.4.1                │
│                                                                       │
│  ┌─ Peripherals (4) ────────────────────────────────────────────────┐│
│  │ ✓ USART2  debug   115200 8N1     PA2/PA3        no DMA          ││
│  │ ✓ USART1  app     115200 8N1     PA9/PA10       DMA1 ch1+ch2    ││
│  │ ✓ GPIO    led     output         PA5            (LD4)            ││
│  │ ✓ GPIO    btn     input pull-up  PC13           (B1)             ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                       │
│  ┌─ Build ───────────────────────┐  ┌─ Memory ─────────────────────┐ │
│  │ Last:    12 s ago  ✓          │  │ Flash  32.4 KB / 128 KB      │ │
│  │ Profile: Debug                │  │ ▓▓▓▓▓▓▓▓░░░░░░░░░░░░░  25%  │ │
│  │ Errors:   0                   │  │                              │ │
│  │ Warns:    2                   │  │ RAM     4.1 KB /  36 KB      │ │
│  │ Size:    32.4 KB              │  │ ▓▓░░░░░░░░░░░░░░░░░░░  11%  │ │
│  └───────────────────────────────┘  │ Stack    2.0 KB              │ │
│                                     └──────────────────────────────┘ │
│                                                                       │
│  ┌─ Recent activity ─────────────────────────────────────────────── ┐│
│  │ 12 s   build       ✓ ok    32.4 KB                              ││
│  │  3 m   add uart    ✓ USART1 PA9/PA10 + DMA                      ││
│  │  5 m   add gpio    ✓ btn PC13                                   ││
│  │ 10 m   alloy new   ✓ scaffolded from nucleo_g071rb              ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                       │
│  b build  · f flash · d debug · a add · c clocks · m memory · q quit │
╰───────────────────────────────────────────────────────────────────────╯
```

### Data sources

| Panel | Source |
|---|---|
| Board / chip identity | `alloy.toml [board]` + alloy-devices-yml IR |
| Toolchain status | `core.toolchain.detect()` |
| Probe status | `core.flash.detect_probes()` |
| Clock summary | `alloy.toml [clocks]` + IR `system_clock_profiles` |
| Peripherals list | `alloy.toml [[peripherals]]` |
| Build status | `.alloy/cache/last_build.json` |
| Memory usage | parse last `.elf` + linker map |
| Recent activity | tail of `.alloy/cache/events.jsonl` |

### Interactions

| Key | Action |
|---|---|
| `b` | trigger `alloy build` (transitions to Build Log screen) |
| `f` | `alloy flash` (Flash Progress screen) |
| `d` | `alloy debug` (spawns external GDB session) |
| `a` | open Peripheral Add picker (sub-menu: uart / gpio / spi / …) |
| `c` | open Clock Tree screen |
| `m` | open Memory Map screen |
| `Ctrl+P` | command palette |
| `↑↓` | navigate the activity log |
| `Enter` on a peripheral | open its detail / edit screen |
| `?` | help overlay |
| `q` | quit |

### Empty states

If no peripherals configured: peripheral panel says
`No peripherals yet.  Press 'a' to add one.`  with a hint to the
command palette.

If never built: build panel says `Never built.  Press 'b'.`

---

## Screen 2 — Board picker

The **first thing a new user sees** via `alloy new`.  Determines the
chip, debug UART, LED, MCUboot offsets, default clock profile.

### Layout

```
╭──────────────────────────────── alloy boards ─────────────────────────────────╮
│ Search: nucleo_                                                  showing 4/11 │
│                                                                                │
│ Filter   Vendor    [✓ st] [ nordic] [ nxp] [ esp] [ rpi] [ microchip]         │
│          ISA       [✓ Cortex-M0+] [ M4] [ M7] [ RV32] [ Xtensa] [ AVR]        │
│          Has       [ ] USB [ ] Ethernet [ ] BLE [ ] CAN [ ] WiFi              │
│          Tier      [✓ 1] [ 2] [ 3]                                            │
│                                                                                │
│ ▶ nucleo_g071rb       STM32G071RB · Cortex-M0+ · 128 KB flash · LD4 · USART2 │
│   nucleo_g0b1re       STM32G0B1RE · Cortex-M0+ · 512 KB flash · LD4 · USB-C  │
│   nucleo_g030f6       STM32G030F6 · Cortex-M0+ ·  32 KB flash                │
│   nucleo_f401re       STM32F401RE · Cortex-M4F · 512 KB flash                │
│                                                                                │
│ ┌─ nucleo_g071rb · selected ──────────────────────────────────────────────┐  │
│ │ Vendor:        ST                                                        │  │
│ │ MCU:           STM32G071RBT6                                             │  │
│ │ Core:          Cortex-M0+ · 64 MHz                                       │  │
│ │ Flash / RAM:   128 KB / 36 KB                                            │  │
│ │ Package:       LQFP-64                                                   │  │
│ │ Probe:         ST-Link v3 (on-board) · openocd / probe-rs               │  │
│ │ Debug UART:    USART2 · PA2/PA3 · 115200                                 │  │
│ │ LED:           LD4 · PA5 · active high                                   │  │
│ │ Button:        B1 · PC13                                                 │  │
│ │ Clock:         default_pll_64mhz (HSI 16 → PLL ×16/÷4 → SYSCLK 64)      │  │
│ │ MCUBoot:       primary @ 0x08008000 · secondary @ 0x08018000 · 64 KB    │  │
│ │ Tier:          1 (canary admitted)                                       │  │
│ │ Examples:      blink, uart_logger, gpio_button, dma_uart_loopback        │  │
│ └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ↑↓ navigate · / search · Tab filter · Enter select · F2 details · q quit     │
╰────────────────────────────────────────────────────────────────────────────────╯
```

### Custom widgets

- **`FacetedFilter`** — multi-section toggle widget for vendor / ISA /
  has-feature / tier.  Clicks AND together.
- **`BoardListPane`** — scrollable list with right-side details
  pane showing on selection.

### Data sources

- Board catalog from alloy/boards/ + cache.
- Per-board `board.json`.
- Cross-reference to alloy-devices-yml IR for "core" / "clock max" /
  "package" details.

### Interactions

| Key | Action |
|---|---|
| `↑↓` | navigate boards |
| `/` | enter fuzzy search |
| `Tab` | move focus between search / filter / list |
| `Space` | toggle filter chip |
| `Enter` | select board (transitions to: project name prompt → Dashboard) |
| `F2` | expand details into full-screen view |
| `q` | quit without selecting |

### Filtering

Boards filter via:
- Free text (matches board_id, mcu, vendor, family)
- Vendor / ISA / Tier chips
- "Has" capabilities (USB / ETH / BLE / WiFi / CAN) — derived from IR

Updates incrementally — no debouncing perceptible.

---

## Screen 3 — Peripheral assignment (the killer feature)

This is the screen that decides whether `alloy-cli` is taken
seriously.  We ship CubeMX-quality pin assignment **in the terminal**,
**cross-vendor**, **type-validated**, **scriptable**.

### Layout

```
╭──────────────── alloy add uart · stm32g071rb · LQFP-64 ───────────────────────╮
│                                                                                │
│  Peripheral:  ◉ USART1   ○ USART2 (used: debug)   ○ USART3   ○ USART4         │
│  Name:        [ app                       ]                                    │
│                                                                                │
│  ┌─────────────────── Pinout (LQFP-64, top view) ────────────────────────┐   │
│  │  64─────────────────────49                                              │   │
│  │ │                         │     1  ▣ VBAT                              │   │
│  │ │           STM32          │     2  ◉ PC13   GPIO  · btn (input)       │   │
│  │ │          G071RB          │     3  ◉ PC14                             │   │
│  │ │                         │     ... (sequential by pin number)         │   │
│  │ 48                       17│    17  ◉ PA0                              │   │
│  │  └─────────────────────────┘    18  ◉ PA1                              │   │
│  │                                  19  ► PA2    USART2_TX (debug)        │   │
│  │                                  20  ► PA3    USART2_RX (debug)        │   │
│  │                                  21  ► PA5    GPIO   · led             │   │
│  │                                  29  ◆ PA9    USART1_TX (AF7)          │   │
│  │                                  30  ◆ PA10   USART1_RX (AF7)          │   │
│  │                                                                         │   │
│  │  ◉ free   ◆ candidate   ► assigned   ✗ reserved   ▣ power              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
│  ▼ TX pin  [ PA9   ▾ ]   AF7   alt: PB6 (AF0), PC4 (AF1)                      │
│  ▼ RX pin  [ PA10  ▾ ]   AF7   alt: PB7 (AF0), PC5 (AF1)                      │
│                                                                                │
│  DMA   [✓] enabled                                                             │
│         TX → DMA1 ch1   ✓ free       (alt: ch2 · ch3 · ch4 · ch5)             │
│         RX → DMA1 ch2   ✓ free       (alt: ch3 · ch4 · ch5)                   │
│                                                                                │
│  Baud rate     [ 115200    ]                                                  │
│  Data bits     ◉ 8   ○ 9   ○ 7                                                │
│  Stop bits     ◉ 1   ○ 0.5  ○ 1.5  ○ 2                                        │
│  Parity        ◉ none  ○ even  ○ odd                                          │
│  Flow control  ◉ none  ○ RTS/CTS                                              │
│                                                                                │
│  ┌─ Validation ─────────────────────────────────────────────────────────┐    │
│  │ ✓ ValidPinAssignment<PA9,  USART1_TX>                                │    │
│  │ ✓ ValidPinAssignment<PA10, USART1_RX>                                │    │
│  │ ✓ ValidDmaBinding<USART1_TX, DMA1_CH1>                               │    │
│  │ ✓ ValidDmaBinding<USART1_RX, DMA1_CH2>                               │    │
│  │ ✓ Baud 115200 within USART1 max (12.5 MHz @ APB1=64 MHz)             │    │
│  │ ✓ No clock conflicts                                                  │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│  Will modify:                                                                  │
│   · alloy.toml                       (+10 lines)                              │
│   · src/peripherals.cpp              (+12 lines)                              │
│                                                                                │
│  Tab navigate · ↑↓ pick · / search · Ctrl+D diff · Ctrl+S apply · Esc back    │
╰────────────────────────────────────────────────────────────────────────────────╯
```

### The `PinoutWidget` — the heart of this screen

Renders a chip's package as a navigable pinout.  Two modes:

- **Compact (default)**: list view, sequential by pin number, one row
  per pin.  Optimised for keyboard navigation.  Works on 80-col.
- **Schematic**: ASCII-art chip outline with pins around the
  perimeter (LQFP / QFN / WLCSP layouts).  Optimised for spatial
  understanding.  Requires ≥ 100-col.

Toggle with `F3`.

Each pin row shows:
- pin number
- glyph + colour for state (free / candidate / assigned / reserved)
- pin name (PA0, PB12, etc.)
- current assignment if any (signal name or function)

When a peripheral is being added:
- Compatible pins are highlighted as **candidates** (◆ magenta)
- Already-assigned pins are dimmed but visible
- Reserved pins (debug, power, NRST) are red ✗ and unselectable

The widget answers: "for this peripheral + signal, which pins can I
use?"  All data from `connection_candidates[(pin, signal)]` in the IR.

### Smart defaults

When the user lands on this screen:

1. **Peripheral**: pre-selects the lowest-numbered free instance.
2. **TX/RX pins**: pre-selects the *first* candidate pair (by pin
   number) that doesn't conflict with assigned pins.
3. **DMA**: enabled by default if the peripheral supports it and free
   channels exist.
4. **DMA channels**: lowest-numbered free channels for TX and RX
   respectively.
5. **Baud / data bits / stop / parity**: 115200, 8, 1, none.

The user can override anything; the screen re-validates live.

### Validation layer

Live, per-keystroke validation.  Each constraint is one row in the
validation panel.  Failure modes:

- **Pin not capable**: row turns red with `✗ PA12 cannot drive USART1_TX (not in alternate function table)`
- **Pin already assigned**: `✗ PA9 already drives SPI1_MOSI`
- **DMA channel conflict**: `✗ DMA1 ch1 already bound to USART2_TX`
- **Baud out of range**: `✗ Baud 5 000 000 exceeds USART1 max 4 000 000 @ APB1=64 MHz`

Apply (`Ctrl+S`) is **disabled** while any validation row is failing.

### Diff preview (`Ctrl+D`)

Opens the global diff modal (Screen 9) with the proposed changes:

```
╭─ Apply add uart? ──────────────────────────────────────────────────────────╮
│                                                                            │
│ alloy.toml                                                                 │
│ @@ +/-                                                                     │
│ +[[peripherals]]                                                           │
│ +kind        = "uart"                                                      │
│ +name        = "app"                                                       │
│ +peripheral  = "USART1"                                                    │
│ +tx          = "PA9"                                                       │
│ +rx          = "PA10"                                                      │
│ +baud        = 115200                                                      │
│ +dma         = true                                                        │
│                                                                            │
│ src/peripherals.cpp                                                        │
│ @@ +/-                                                                     │
│  // existing peripherals omitted                                           │
│ +inline alloy::Uart<board::USART1> app_uart{                               │
│ +    {.tx_pin = PA9, .rx_pin = PA10, .baud = 115200u, .dma = true}        │
│ +};                                                                        │
│                                                                            │
│  Apply [Y] · Cancel [N] · Edit again [E]                                  │
╰────────────────────────────────────────────────────────────────────────────╯
```

### Interactions

| Key | Action |
|---|---|
| `Tab / Shift+Tab` | move focus between fields |
| `↑↓` | navigate within current field |
| `Enter` | activate dropdown / commit input |
| `Space` | toggle checkbox / radio |
| `F3` | toggle pinout view (compact / schematic) |
| `/` | filter pinout list |
| `Ctrl+D` | preview diff |
| `Ctrl+S` | apply (validates first) |
| `Ctrl+Z` | undo last change in this session |
| `Esc` | back to dashboard (prompts if unapplied changes) |

### CLI parity

Every TUI knob has a `alloy add uart …` flag:

```bash
alloy add uart \
    --name app --peripheral USART1 \
    --tx PA9 --rx PA10 --baud 115200 \
    --dma --tx-dma DMA1_CH1 --rx-dma DMA1_CH2 \
    --apply
```

Without `--apply`, prints the diff and exits with 0.  Same diff the
TUI would show.

### Other peripheral kinds

This same screen template applies to all `alloy add <kind>`:

- **gpio**: pin + mode (input/output/od/pp) + pull (none/up/down) +
  speed + initial state + label.
- **spi**: peripheral + mode + sck/miso/mosi/cs pins + clock prescaler
  + frame format + DMA + cs is software/hardware.
- **i2c**: peripheral + sda/scl pins + speed mode (standard/fast/+) +
  pullups + 7/10-bit addressing + DMA.
- **timer**: peripheral + count direction + prescaler + period +
  trigger + master/slave config.
- **pwm**: timer instance + channels + polarity + dead-time +
  alignment.
- **adc**: instance + channels + sample time + resolution +
  oversampling + DMA.
- **can / eth / usb / sdmmc / qspi / dac / rtc / dma**: similar.

Each kind reuses the same `PinoutWidget`, `ValidationPanel`, and
`DiffPreview`.  Per-kind layout differs only in the body fields.

---

## Screen 4 — Clock tree

A **navigable visual graph** of the chip's clock topology.  Lets the
user pick the system clock profile and see its consequences.

### Layout (default)

```
╭─────────────────────────── alloy clocks · stm32g071rb ────────────────────────╮
│  Profile:  ▾ default_pll_64mhz                                                 │
│            (HSI16 → PLL ×16/÷4 → SYSCLK 64 MHz)                                │
│                                                                                │
│   ┌── Sources ─┐                                                               │
│   │ HSE   8 MHz   ☐ disabled                                                   │
│   │ HSI16 16 MHz  ◉ enabled  ←──┐                                              │
│   │ LSI    32 kHz ☐                                                           │
│   │ LSE    32.768 kHz  ☐                                                      │
│   └─────────────┘            │                                                 │
│                              │                                                 │
│   ┌── PLL ───────────────────┴──┐                                              │
│   │ source: HSI16                │                                             │
│   │ M = 1   N = 16   R = 4       │                                             │
│   │ output:    HSI16 × 16 / 4 = 64 MHz │                                       │
│   └────────────────────────────┬───┘                                           │
│                                │                                               │
│                                ▼                                               │
│   ┌── SYSCLK ─────────────┐   PLL_R                                            │
│   │ source:  ◉ PLL    ○ HSI16    ○ HSE    ○ LSI/LSE                           │
│   │ rate:    64 MHz                                                            │
│   └───────────────────┬───┘                                                    │
│                       ▼                                                         │
│   ┌── HCLK (AHB) ─────┐    ÷1                                                  │
│   │ rate: 64 MHz      │                                                         │
│   └─┬─────────────────┘                                                         │
│     │                                                                           │
│     ├─► PCLK1 (APB1)  ÷1  64 MHz                                              │
│     │      ├─ USART2 ✓ (debug)                                                 │
│     │      ├─ I2C1                                                              │
│     │      ├─ TIM2                                                              │
│     │      └─ DAC1                                                              │
│     │                                                                           │
│     ├─► PCLK2 (APB2)  ÷1  64 MHz                                              │
│     │      ├─ USART1 ✓ (app)                                                   │
│     │      ├─ TIM1                                                              │
│     │      ├─ ADC1                                                              │
│     │      └─ SPI1                                                              │
│     │                                                                           │
│     └─► Cortex-M0+ core 64 MHz                                                 │
│                                                                                │
│  Profiles  default_pll_64mhz · low_power_hsi · custom_user                     │
│                                                                                │
│  ↑↓ navigate node · Enter edit · p switch profile · n new · Ctrl+D diff       │
╰────────────────────────────────────────────────────────────────────────────────╯
```

### `ClockTreeWidget`

Renders `device.clock_nodes` + `clock_selectors` as a navigable
node-link diagram.  Each node displays:
- name
- current rate (computed from upstream + divider)
- enabled / disabled state
- attached peripherals (children)

Selectors render as multi-choice radio rows; the user can change the
selected source and see the rate cascade.

### Editing clocks

Pressing `Enter` on:
- A **source** (HSI16 / HSE / LSI / LSE): toggles enabled, prompts
  for crystal frequency for HSE/LSE.
- A **PLL**: opens a sub-modal to edit M / N / R / etc.  Shows the
  output frequency live.
- A **SYSCLK selector**: radio change cascades to all downstream
  rates immediately.
- A **prescaler** (HCLK/PCLK1/PCLK2): cycle through valid divisors.

Live validation flags:
- "PCLK1 76 MHz exceeds APB1 max 64 MHz" → red.
- "USART2 max baud at PCLK1=76 = 9.5 Mbps; current config 115 200
  OK" → info.

### Custom profiles

`p` switches between predefined profiles (HSI / PLL / LP).  `n`
saves the current state as a new profile in `alloy.toml [clocks]`.

### CLI parity

```bash
alloy clocks set-profile default_pll_64mhz
alloy clocks set-pll --source HSI16 --m 1 --n 16 --r 4
alloy clocks save-profile custom_radio
```

---

## Screen 5 — DMA matrix

Phase 5.  Gives a bird's-eye view of which DMA channels are bound to
what.

### Layout

```
╭───────────────── alloy dma · stm32g071rb ─────────────────────────────────╮
│ Controller: ◉ DMA1   ○ DMAMUX                                              │
│                                                                            │
│            ch1     ch2     ch3     ch4     ch5     ch6     ch7             │
│ USART1_TX  ●                                                                │
│ USART1_RX           ●                                                       │
│ USART2_TX                   ◯                                              │
│ USART2_RX                           ◯                                      │
│ SPI1_TX                                     ◯                              │
│ SPI1_RX                                              ◯                     │
│ I2C1_TX                                                       ◯           │
│ I2C1_RX                                                                    │
│ ADC1                                                                       │
│                                                                            │
│ ● bound  ◯ available  ⊘ conflict                                          │
│                                                                            │
│ Selected: USART1_TX → DMA1 ch1                                             │
│ Priority: ◉ low  ○ medium  ○ high  ○ very high                             │
│ Mode:     ◉ single  ○ circular                                             │
│                                                                            │
│ ↑↓←→ navigate cell · Enter bind/unbind · Ctrl+D diff · Esc back           │
╰────────────────────────────────────────────────────────────────────────────╯
```

Useful when adding a peripheral and there are channel conflicts.
Lets the user re-route bindings.

---

## Screen 6 — Memory map

Phase 5.  Shows flash sections, RAM regions, MCUboot offsets,
stack/heap.

### Layout

```
╭───────────────── alloy memory · my-firmware ──────────────────────────────╮
│                                                                            │
│ Flash (128 KB total)                                                       │
│ 0x08000000 ┌─────────────────────────────────────────┐                    │
│            │ MCUboot bootloader                       │ 32 KB              │
│ 0x08008000 ├─────────────────────────────────────────┤ ← primary slot     │
│            │ App image header                         │ 1 KB               │
│            │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░ │ 32.4 KB used       │
│            │ .text  18.2 KB                           │                    │
│            │ .rodata 4.1 KB                           │ 64 KB slot total  │
│            │ free  31.5 KB                            │                    │
│ 0x08018000 ├─────────────────────────────────────────┤ ← secondary slot   │
│            │ (empty, reserved for OTA)                │ 64 KB              │
│ 0x08028000 └─────────────────────────────────────────┘                    │
│                                                                            │
│ RAM (36 KB total)                                                          │
│ 0x20000000 ┌─────────────────────────────────────────┐                    │
│            │ .data    1.0 KB                          │                    │
│            │ .bss     3.1 KB                          │                    │
│            │ heap     0 KB (no malloc)                │                    │
│            │ free    29.9 KB                          │                    │
│            │ stack    2.0 KB top                      │                    │
│ 0x20009000 └─────────────────────────────────────────┘                    │
│                                                                            │
│ ↑↓ navigate region · Enter details · F2 sym view · q quit                  │
╰────────────────────────────────────────────────────────────────────────────╯
```

### Data sources

- IR `memories[]` for region definitions.
- ELF + linker `.map` file for actual usage.
- `alloy.toml [mcuboot]` for slot offsets.

`F2` switches to a per-symbol view sorted by size (helps optimise
flash usage).

---

## Screen 7 — Build log (live)

Streamed during `alloy build`.  Replaces a tail of cmake/ninja output.

### Layout

```
╭────────────── alloy build · my-firmware ────────────────────────────────╮
│                                                                          │
│  Profile:  Debug          Toolchain:  arm-none-eabi-gcc 13.2.0          │
│  Started:  2 s ago        ETA:         ~6 s                             │
│                                                                          │
│  ┌─ Phases ─────────────────────────────────────────────────────────┐  │
│  │ ✓ Configure CMake                                       0.4 s     │  │
│  │ ✓ Generate device headers (alloy-codegen)               0.2 s     │  │
│  │ ◉ Compile sources                                       running   │  │
│  │   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░  18 / 24                          │  │
│  │ ○ Link                                                            │  │
│  │ ○ Post-process (.elf → .hex / .bin / .map)                       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Output ──────────────────────────────────────────────────────────┐ │
│  │ [ 76%] Building CXX object src/peripherals.cpp.o                  │ │
│  │ [ 81%] Building CXX object .alloy/generated/stm32g071rb/...       │ │
│  │ [ 84%] Building CXX object src/main.cpp.o                         │ │
│  │ src/main.cpp:42: warning: unused variable 'temp'                  │ │
│  │ [ 88%] Building CXX object alloy/drivers/sensor/...               │ │
│  │ ...                                                                │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ↑↓ scroll · Ctrl+E filter errors · Ctrl+W filter warnings · q cancel  │
╰──────────────────────────────────────────────────────────────────────────╯
```

When build finishes, transitions automatically to a build summary
panel showing memory delta vs previous build.

### Live error rendering

Compiler warnings/errors are parsed and rendered as **navigable
items**.  Pressing `Enter` on an error opens it in `$EDITOR` at the
exact line/column.

---

## Screen 8 — Flash progress

Streamed during `alloy flash`.  Shows probe + transfer status.

### Layout

```
╭─────────────── alloy flash · my-firmware ──────────────────────────────╮
│                                                                          │
│  Probe:    J-Link · serial 778100123 · firmware 7.96b                   │
│  Target:   STM32G071RB · DAP detected · halt OK                         │
│  Image:    .alloy/build/my-firmware.elf · 32.4 KB                       │
│                                                                          │
│  ┌─ Transfer ────────────────────────────────────────────────────────┐  │
│  │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░  72%   24.0 / 32.4 KB   │  │
│  │ Speed: 410 KB/s · ETA 0 s                                         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Output ──────────────────────────────────────────────────────────┐  │
│  │ erasing sector 0x08000000-0x08020000                              │  │
│  │ writing 32.4 KB to 0x08000000                                      │  │
│  │ verifying...                                                       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  q cancel                                                                │
╰──────────────────────────────────────────────────────────────────────────╯
```

After completion, transitions to "reset target?" prompt.

---

## Screen 9 — Diff modal (global)

Used by every screen before applying changes.  Already shown in
Screen 3 example.

### Layout principles

- Side-by-side or unified, user-toggleable (`F4`).
- Syntax-highlighted (Rich's pygments integration).
- Keyboard navigation: `n / p` next/prev hunk, `q` close.
- Apply (`Y`) commits files atomically.  All-or-nothing — no partial
  apply, no torn state.

---

## Screen 10 — Command palette (`Ctrl+P`)

VS Code-style fuzzy search across every command + every screen + every
recent project + every documented action.

### Layout

```
╭─ Command palette ──────────────────────────────────────────────────╮
│ > add uar█                                                          │
│                                                                     │
│ ▶ Add UART peripheral                              [a → uart]      │
│   Add USB peripheral                               [a → usb]       │
│   Show UART semantic table                         alloy ir uart  │
│   Open UART driver source (alloy/src/hal/uart)     [code]          │
│   Recent: app uart on USART1                       [edit]          │
│                                                                     │
│ ↑↓ pick · Enter run · Esc cancel                                   │
╰─────────────────────────────────────────────────────────────────────╯
```

Sources of suggestions:
- Every CLI command and subcommand.
- Every TUI screen mount.
- Every recent action from `.alloy/cache/events.jsonl`.
- Documented topics from `alloy help`.

---

## Screen 11 — Doctor

`alloy doctor`.  Diagnostic of the developer's machine.

### Layout

```
╭───────────────── alloy doctor ─────────────────────────────────────╮
│                                                                     │
│ Python                                                              │
│  ✓ python 3.13.2                  required: 3.11+                   │
│                                                                     │
│ alloy-cli                                                           │
│  ✓ alloy-cli 0.5.0                                                  │
│  ✓ alloy-codegen 0.4.1            in alloy.toml: >=0.4,<0.5         │
│                                                                     │
│ Toolchains                                                          │
│  ✓ arm-none-eabi-gcc 13.2.0       at /opt/homebrew/bin              │
│  ✗ riscv64-unknown-elf-gcc        not found                         │
│      install:  brew install riscv-elf-gcc                           │
│  ✗ xtensa-esp32s3-elf-gcc         not found                         │
│      install:  espressif install (https://...)                      │
│                                                                     │
│ Probes                                                              │
│  ✓ probe-rs 0.24.0                                                  │
│  ✓ J-Link · serial 778100123 · plugged                              │
│  ○ ST-Link                        not detected                      │
│                                                                     │
│ Project (my-firmware)                                               │
│  ✓ alloy.toml valid                                                 │
│  ✓ devices submodule initialised                                    │
│  ⚠ alloy 0.7.3 → 0.7.5 available  alloy update                      │
│                                                                     │
│ Network                                                             │
│  ✓ github.com reachable                                             │
│  ✓ pypi.org reachable                                               │
│                                                                     │
│ Press 'r' to re-run, 'f' to fix issues automatically (when safe)   │
╰─────────────────────────────────────────────────────────────────────╯
```

### Auto-fix

`f` triggers fixers for issues marked **auto-fixable**:
- Install missing Python deps via pip.
- Initialise the alloy-devices-yml submodule.
- Update alloy versions per the lockfile.

Never auto-installs system toolchains (asks for confirmation, prints
the install command, lets the user run it).

---

## Screen 12 — Onboarding wizard

First-time `alloy` invocation in a fresh directory or `alloy new`
without args.

### Flow

```
1.  Welcome — what alloy-cli is, two-line intro
2.  Project name                          — text input
3.  Pick a board                          — Board picker (Screen 2)
4.  Pick a clock profile                  — Clock tree (Screen 4)
5.  Add a starter peripheral?             — yes / no
       if yes: Peripheral picker (Screen 3)
6.  Confirm — show the full diff that will be created
7.  Build immediately?                    — yes / no
       if yes: Build log (Screen 7)
```

Each step has a "skip" option.  Step counter visible at top.  `Esc`
exits to a partially-configured project (writes `alloy.toml` with
what's been chosen so far, leaves a `# TODO: continue with 'alloy
add'` comment).

### Why a wizard

A first-time embedded user does not know:
- That arm-gcc needs to be on PATH
- That probe-rs is a thing
- That clock profile choice matters

The wizard threads the doctor into onboarding so the user finds
problems before they hit them in `alloy build`.

---

## Custom widget catalogue

Reused across screens.  Phase-3 / Phase-5 proposals each ship 1-2.

| Widget | Used by | Phase | LOC est. |
|---|---|---|---|
| `PinoutWidget` | 3 (peripheral add), 4 (clocks for pin-bound nodes) | 3 | ~500 |
| `ClockTreeWidget` | 4, 1 (mini-summary) | 3 | ~600 |
| `DmaMatrixWidget` | 5, 3 (sub-panel), 1 (mini-summary) | 5 | ~400 |
| `MemoryMapWidget` | 6, 1 (mini-summary), 7 (post-build) | 5 | ~300 |
| `DiffWidget` | 9, embedded everywhere | 3 | ~250 |
| `ValidationPanel` | 3, 4, every "add"/"edit" screen | 3 | ~150 |
| `FacetedFilter` | 2 (boards), 3 (peripheral picker) | 3 | ~200 |
| `CommandPalette` | 10, global | 3 | ~250 |
| `ToolchainBadge` | 11 (doctor), 1 (dashboard top bar) | 5 | ~80 |
| `LiveLogPane` | 7 (build), 8 (flash) | 3 | ~200 |

## Theming

Two built-in themes:

- **Default (dark)** — the colour-coded scheme described above
- **High contrast** — for accessibility / projector / sunlight

Auto-detect from `$COLORFGBG` env or `--theme` flag.  No web theme
nonsense; keep the palette tight.

## Accessibility

- All glyphs paired with text labels in screen-reader mode
  (`--screen-reader` or detected via `$NVDA_RUNNING` etc).
- Tab order documented per screen; never trap focus.
- High-contrast theme uses ≥7:1 contrast ratios.
- `NO_COLOR=1` and `TERM=dumb` produce a degraded but usable text-only
  output.

## Snapshot testing

Every screen has snapshot tests via `pytest-textual-snapshot`:

```python
def test_dashboard_renders(app):
    async with app.run_test() as pilot:
        await pilot.press("a", "u")  # dashboard → add → uart
        assert pilot.app.screen == PeripheralAddScreen
    snap = pilot.app.export_screenshot()
    assert snap == load_golden("dashboard_add_uart.svg")
```

CI fails on visual regression unless explicitly approved with
`--update-snapshots`.

## Deferred to post-v1

- **Web UI** — same widgets re-skinned via Textual's web mode.  Could
  ship as `alloy ui --web` opening localhost.
- **Multi-board project view** — when one project targets multiple
  boards (e.g., dev + prod variants).
- **Peripheral conflict resolver wizard** — when adding a peripheral
  conflicts with an existing one, walk through alternatives.
- **Visual schematic export** — `alloy export schematic` produces a
  KiCad symbol or PDF of the chosen pinout.

---

## What "top" means

We are top if and only if these claims are true after Phase 3:

1. A user new to embedded can `alloy new --board pico` → working
   firmware in **under 5 minutes**.
2. A CubeMX power user can `alloy add uart` and feel **at home in
   under 30 seconds**.
3. The pin picker handles **8 500+ chips** without per-chip code.
4. Snapshot tests cover **every screen** with ≥80% line coverage.
5. The TUI runs in **plain xterm at 80×24** without breaking.
6. `alloy build` time is **within 50 ms of raw cmake**.
7. All TUI ops have **CLI equivalents** for CI.
8. **Zero hallucination** in the MCP path (every patch passes IR +
   compile-time validation).

Anything less is an iteration target, not a release blocker.
