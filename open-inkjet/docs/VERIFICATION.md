# Verification log

## Verified by running (2026-09-29, in the build sandbox)
- `host/tests`: 8 pytest tests pass (swath 12.7 mm, 300 dpi pitch 0.0847 mm, A4 = 24 swaths, slice round-trip).
- `firmware/tests/test_sched.c`: passes under -Wall -Wextra -Werror with ASan+UBSan (forward, reverse + bidir offset, missed-column handling).
- `cad/carriage_plate.py`: builds; solid is valid; volume equals the hand-computed value (6438.1 mm^3); fits 220 mm bed.

## Sourced but NOT verified (search snippets only; primary pages blocked in the sandbox)
- HP45: 300 nozzles/600 npi, 12.7 mm swath, 12 V, 52 contacts, 18 kHz max, 300 dpi recommended: confirmed by an independent fact-check via search summaries (ytec3d.com page itself blocked; nozzle count also on the HP store page).
- HP45 ~30 ohm heater and ~2 us fire pulse: UNVERIFIED (independent check found no source; pulse width is ink dependent). Measure on the bench.
- Licence identifiers CERN-OHL-S-2.0, GPL-3.0-only, CC-BY-4.0 are valid non-deprecated SPDX IDs (SPDX list v3.29.0). Mixed per-folder licensing under an Apache-2.0 root is standard; a REUSE-style layout (SPDX headers, LICENSES/ dir) is still TODO. GPL/Apache compatibility was not verified from a source, and no legal review has been done.
- MGN9H carriage 20 x 40 x 8 mm, M3 holes 15 x 16 mm (vendor snippets; datasheet PDF unreachable). Measure the real part before printing.
- No pinout, fire-sequence timing, or HP45 cartridge outline is in the repo yet: these must come from bench measurement.

## Needs hardware (cannot be done by software alone)
Everything physical: printhead bench test, motion/encoder registration, paper-feed accuracy, print quality, maintenance station.
