# Verification log

## Verified by running (2026-09-29, in the build sandbox)
- `host/tests`: 8 pytest tests pass (swath 12.7 mm, 300 dpi pitch 0.0847 mm, A4 = 24 swaths, slice round-trip).
- `firmware/tests/test_sched.c`: passes under -Wall -Wextra -Werror with ASan+UBSan (forward, reverse + bidir offset, missed-column handling).
- `cad/carriage_plate.py`: builds; solid is valid; volume equals the hand-computed value (6438.1 mm^3); fits 220 mm bed.

## Sourced but NOT verified (search snippets only; primary pages blocked in the sandbox)
- HP45: 300 nozzles/600 dpi spacing, 12 V, ~30 ohm heater, ~2 us pulse, 18 kHz max (ytec3d.com).
- MGN9H carriage 20 x 40 x 8 mm, M3 holes 15 x 16 mm (vendor snippets; datasheet PDF unreachable). Measure the real part before printing.
- No pinout, fire-sequence timing, or HP45 cartridge outline is in the repo yet: these must come from bench measurement.

## Needs hardware (cannot be done by software alone)
Everything physical: printhead bench test, motion/encoder registration, paper-feed accuracy, print quality, maintenance station.
