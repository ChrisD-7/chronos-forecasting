# Verification log

## Verified by running (2026-09-29, build sandbox; `./run_tests.sh`)
- Host: 26 pytest tests (geometry, slicer nozzle mapping for vdpi 600..50, protocol, sender retransmit/stale-ACK, filter aspect/alpha/16-bit/non-square dpi).
- Firmware: scheduler and parser tests under -Wall -Wextra -Werror with ASan+UBSan; Python-generated frame stream decoded by the C parser (cross-language check).
- CAD: carriage plate builds, valid solid, volume equals hand calculation (6438.1 mm^3), fits 220 mm bed.

## Independent review (subagents + /code-review), all findings reproduced before fixing
- Code review: parser init/reset, halftone speed, alpha, aspect, column-order contract, ACK/retransmit, test vectors. Fixed.
- Firmware audit (fuzz 3M bytes / 300k frames / 300k scheduler runs clean; mutation check 15/20 caught): fixed dir==0 hang, int32 overflow (now int64), config validation (`oi_sched_start` returns status), and added tests that kill the 5 surviving mutants (re-checked: all killed).
- Host audit: fixed non-square dpi distortion, nozzle-count divisibility crash, 16-bit greyscale blank, stale-ACK mis-match (replies now echo the frame CRC; START_PASS carries the swath index).

## Known limits (not fixed)
- Parser is not self-healing mid-frame (0xA5 occurs in payload). Relies on transport timeout + `oi_parser_reset` + per-frame ACK/retransmit; the device-side app layer that sends ACK/NAK and ignores a repeated START_PASS swath index does not exist yet.
- The filter is not a CUPS filter (no PPD/backend). No motor/feed/encoder-hardware drivers exist; the head backend (`fire_column` for HP45) is not written because pinout/timing are unverified.

## Sourced but NOT verified (search snippets only; primary pages blocked in the sandbox)
- HP45: 300 nozzles/600 npi, 12.7 mm swath, 12 V, 52 contacts, 18 kHz max, 300 dpi recommended: confirmed by an independent fact-check via search summaries (ytec3d.com page itself blocked; nozzle count also on the HP store page).
- HP45 ~30 ohm heater and ~2 us fire pulse: UNVERIFIED (independent check found no source; pulse width is ink dependent). Measure on the bench.
- Licence identifiers CERN-OHL-S-2.0, GPL-3.0-only, CC-BY-4.0 are valid non-deprecated SPDX IDs (SPDX list v3.29.0). Mixed per-folder licensing under an Apache-2.0 root is standard; a REUSE-style layout (SPDX headers, LICENSES/ dir) is still TODO. GPL/Apache compatibility was not verified from a source, and no legal review has been done.
- MGN9H carriage 20 x 40 x 8 mm, M3 holes 15 x 16 mm (vendor snippets; datasheet PDF unreachable). Measure the real part before printing.
- No pinout, fire-sequence timing, or HP45 cartridge outline is in the repo yet: these must come from bench measurement.

## Needs hardware (cannot be done by software alone)
Everything physical: printhead bench test, motion/encoder registration, paper-feed accuracy, print quality, maintenance station.
