# Head-drive electronics and controller board (design, not a verified circuit)

Status: block-level design with calculations and consistency checks (`electronics/`), and RP2040 firmware that compiles against
the Pico SDK (`firmware/board/rp2040/`). **No schematic capture, PCB, or analog driver stage exists, and nothing has been powered.**
The analog stage depends on head parameters that are still UNVERIFIED (address drive level and polarity, heater resistance, pulse width).

## Why shift registers
The head needs 22 address + 14 primitive lines = 36 outputs; a Pico exposes 26 usable GPIO (GP0-GP22 and GP26-GP28; GP23-GP25 are internal).
The design uses five 74HC595 (40 outputs: 36 used, 4 to test points) on SPI0, latched by RCLK, with all outputs gated by `OE_N` (active low).
`OE_N` is the fire-pulse gate. The netlist includes a pull-up on `OE_N` and a pull-down on every driver input, so with the MCU in reset or
unprogrammed the outputs are off. **That is the limit of the claim:** if the firmware hangs while `OE_N` is being held low inside a pulse, the
heaters stay energised. A hardware one-shot or watchdog gate would be needed for a stronger guarantee; it is not designed.

## Budgets (`electronics/design.py`, `python3 electronics/design.py`)
| Quantity | Value | Basis |
|---|---|---|
| Heater current | 0.4 A | 12 V (SOURCED) / 30 ohm (UNVERIFIED) |
| Energy per nozzle pulse | 9.6 uJ | 12^2/30 x 2 us (pulse UNVERIFIED) |
| Peak current, 14 heaters (one address on at a time) | 5.6 A for about 2 us | 14 x 0.4 A |
| Bulk capacitance, per pulse, 5% droop | 18.7 uF minimum | Q / (V x droop); a lower bound only |
| Bulk capacitance for a whole fully inked column with no recharge | about 400 uF | 300 nozzles x 0.4 A x 2 us = 240 uC |
| ESR + wiring budget for the peak current | 107 mohm in total | 0.6 V / 5.6 A; loop inductance is NOT modelled |
| Average current over a worst-case column | 1.35 A | 240 uC / column time |
| SPI clock | 8.93 MHz actual (10 MHz requested) | Pico SDK baud algorithm, derated because the 74HC595 clock limit at 3.3 V is UNVERIFIED (found only 4.5 V / 5 V figures) |
| Time per address (5 bytes, latch, 1 us settle, pulse, gap) | 8.1 us | CHOICE values in design.py |
| Worst-case column (all 22 addresses) | 178 us | 22 x 8.1 us |
| Max column rate / carriage speed at 2 counts per dot | 5.6 kHz / 11,250 counts/s | the shift-register sequence is the binding limit, not the 18 kHz head limit |
| Configured cruise speed | 9,000 counts/s | 25% of the head limit; about 20% margin on the figure above |

The first draft assumed 25 MHz SPI, which a 125 MHz Pico cannot produce (the SDK picks 20.8 MHz); an independent review caught it and the derivation
is now computed and tested.

## Circuit simulation of the power stage (`electronics/spice_sim.py`, ngspice 42)
The netlist is generated from `design.py` (12 V rail, 14 heaters of 30 ohm switched together for 2 us, repeated once per address for a whole column, ideal switches with 0.05 ohm on-resistance).
| Scenario | Simulated rail droop | Reading |
|---|---|---|
| One worst pulse, capacitor isolated, 18.7 uF | 4.9% | confirms the per-pulse formula (5%) |
| Whole column, capacitor isolated, 400 uF | 5.0% | confirms the per-column bound |
| Whole column, capacitor isolated, 18.7 uF | 66.7% | the per-pulse minimum is NOT enough without a supply that recharges |
| Isolated, 2200 uF, ESR 150 mohm / 50 mohm | above / below 5% | confirms the 107 mohm ESR budget (droop = I x ESR / V) |
| Whole column, assumed stiff supply (50 mohm, 100 nH, 20 mohm ESR), 470 uF / 1000 uF / 18.7 uF | 1.3% / 1.3% / 3.5% | with a stiff supply the supply carries the load; the result depends entirely on that assumption |
**Guidance that follows:** size the bulk capacitor for the measured supply impedance with this simulator; 400 uF is the safe bound if you cannot guarantee recharge, and 470 uF or more with an ESR under 107 mohm
is a sensible starting point. The simulator uses ideal switches: it says nothing about the real driver FETs, gate drive, the address stage, loop inductance beyond the single 100 nH element, or the head itself.

## Netlist and checks (`electronics/netlist.py`)
118 nets at block level with pin kinds (out/in/power/passive). Per chip: VCC, GND, SRCLK, RCLK, OE_N, SRCLR_N (tied high), SER, QH' and Q A-H.
Rules: no floating nets, no pin on two nets, no input without a driver, no two drivers, power pins on power nets, every declared component pin
connected, no reused GPIO, OE_N pull-up and per-output pull-downs present, head contact name must match its net, shift-register chain continuity.
**13 injected defects are each caught** (floating net, double pin, missing ground, swapped head contacts, broken chain, unclocked chip, floating clear,
unpowered driver, missing pull-up, missing pull-down, two drivers, undriven input, unsourced supply).
A separate test simulates the real byte sequence of `sr_shift_and_latch()` through a 5-chip 74HC595 model and checks that every address/primitive bit
lands on the intended head line via the netlist (and that a swapped output pair is detected). `board_config.h` pin numbers are checked against the netlist.
Limits: the driver stages are blocks, not circuits; pin kinds are my own annotations, not datasheet-derived.

## Firmware safety defaults (`firmware/board/rp2040/`)
- Outputs are disabled and shift registers cleared before anything else at boot; GPIO levels are set before the pins become outputs (so OE_N and the
  driver enables do not glitch low); motors are disabled at boot.
- **DRY by default:** `head_map.h` ships with `OI_HEAD_MAP_VERIFIED 0`. The board then uses a head that never pulses (everything moves, nothing fires,
  LED off). To arm: measure the nozzle map (docs/BENCH.md), define `OI_HEAD_MAP`, set the flag to 1; `oi_matrix_head_init` still rejects duplicate or
  out-of-range entries and falls back to dry.
- Fire sequence: shift and latch with OE_N high, wait `OI_SETTLE_NS` (about 1 us, 41 loop iterations), then OE_N low for `OI_PULSE_NS` (83 iterations of a
  3-cycle loop, about 2 us) with interrupts masked. The routine runs from RAM. The loop counts were checked in the disassembly; the real width also
  includes GPIO and loop-entry cycles and **must be measured with a scope**. A first version of this loop was 3x too long (found in review).
- Two cores: core 0 = USB receive and `oi_app_feed` (answers BUSY at once), core 1 = `oi_app_service` (passes, maintenance). The pass hand-off sets
  `busy` before clearing `pass_ready` (a review found the reverse order let the receiver accept a new header mid-hand-off); reply writes are mutex-protected.
- Carriage: step timer with a spin lock around start/stop, positive period arithmetic (the first version fed the SDK's negative delay into the ramp, so it
  would never have accelerated and `drive(0)` would have hung), a stop timeout, homing against the left switch, braking started at the last column.

## Not done / must be measured before power-up
1. Analog driver stage: level shifting to the address FET gates, the 14 high-current primitive switches, current limiting, fuse; needs the measured address
   drive level/polarity, heater resistance and pulse width. Supply decoupling to the numbers above, including ESR and loop inductance.
2. Schematic capture and PCB layout (KiCad or similar), including the pogo-pin head connector.
3. Encoder reader choice, stepper drivers, end-stop and paper-sensor wiring details; home-switch polarity is assumed (active low).
4. Scope the actual pulse and settle timing; verify SPI at 3.3 V against the exact 74HC595 part's datasheet (or use a 3.3 V-rated 74LV/74AHC595).
5. Steps-per-count calibration (assumed 1.0) and stepper start/stop speed.
