# Head-drive electronics and controller board (design, not a verified circuit)

Status: block-level design with calculations and consistency checks (`electronics/`), and RP2040 firmware that compiles against
the Pico SDK (`firmware/board/rp2040/`). **No schematic capture, PCB, or analog driver stage exists, and nothing has been powered.**
The analog stage depends on head parameters that are still UNVERIFIED (address drive level and polarity, heater resistance, pulse width).

## Why shift registers
The head needs 22 address + 14 primitive lines = 36 outputs; an RP2040 board exposes 26 usable GPIO. The design uses five 74HC595
(40 outputs: 36 used, 4 brought out to test points) on SPI0, latched by RCLK, with all outputs gated by `OE_N` (active low). `OE_N` is the
fire-pulse gate: with it pulled high the heaters cannot be energised, so a crashed or unprogrammed MCU cannot leave a heater on.

## Budgets (`electronics/design.py`, `python3 electronics/design.py`)
| Quantity | Value | Basis |
|---|---|---|
| Heater current | 0.4 A | 12 V (SOURCED) / 30 ohm (UNVERIFIED) |
| Energy per nozzle pulse | 9.6 uJ | 12^2/30 x 2 us (pulse UNVERIFIED) |
| Worst-case simultaneous heaters | 14 (one address at a time) | address/primitive scheme (patent snippet) |
| Peak current | 5.6 A for about 2 us | 14 x 0.4 A |
| Minimum bulk capacitance for 5% droop | 18.7 uF (fit several times that, low ESR) | Q / (V x droop) |
| Time per address (5 SPI bytes at 25 MHz, latch, settle, pulse, gap) | 5.2 us | CHOICE values in design.py |
| Worst-case column (all 22 addresses) | 114 us | 22 x 5.2 us |
| Max column rate / carriage speed at 2 counts per dot | 8.7 kHz / 17,500 counts/s | binding limit is the SPI-driven sequence, not the 18 kHz head limit |
| Configured cruise speed | 9,000 counts/s | 25% of the head limit; leaves margin (tested) |

## Netlist and checks (`electronics/netlist.py`)
117 nets at block level: MCU pins, shift-register chain, 22 address and 14 primitive driver stages (blocks only), the 52-contact head connector
(22 address + 14 primitive + 14 primitive commons + 2 contacts of unknown function, left on test points), power and ground. ERC-style rules:
no floating nets, no pin on two nets, no reused GPIO, every head contact assigned exactly once, every shift-register output used once.
The tests also confirm that `firmware/board/rp2040/board_config.h` pin numbers equal the netlist's MCU pins. The rules caught two defects in the first
draft (floating spare outputs; all 14 returns sharing one ground pad), which were fixed.

## Firmware safety defaults (`firmware/board/rp2040/`)
- Outputs are disabled and shift registers cleared before anything else at boot; motors are disabled at boot.
- **DRY by default:** `head_map.h` ships with `OI_HEAD_MAP_VERIFIED 0`. The board then uses a head that never pulses (everything moves, nothing fires,
  LED off). To arm: measure the nozzle map (docs/BENCH.md), define `OI_HEAD_MAP`, set the flag to 1; `oi_matrix_head_init` still rejects duplicate or
  out-of-range entries and falls back to dry.
- Fire pulse runs from RAM with interrupts disabled; width is `OI_PULSE_NS` (UNVERIFIED; start short on the bench).
- Two cores: core 0 = USB receive and `oi_app_feed` (answers BUSY at once), core 1 = `oi_app_service` (passes, maintenance). Reply writes are mutex-protected.

## Not done / must be measured before power-up
1. Analog driver stage: level shifting to the address FET gates, the 14 high-current primitive switches, current limiting, fuse; needs the measured address
   drive level/polarity, heater resistance and pulse width.
2. Schematic capture and PCB layout (KiCad or similar), including the pogo-pin head connector.
3. Encoder reader choice, stepper drivers, end-stop and paper-sensor wiring details.
4. Actual timing of the pulse (scope), SPI at 3.3 V into 74HC595 (verify with the exact part's datasheet), supply droop under a full column.
