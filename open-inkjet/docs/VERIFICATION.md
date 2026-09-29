# Verification log (2026-09-29, build sandbox). Reproduce with `./run_tests.sh --mutate`.

## Tested by running code
- **Host, 42 pytest tests:** geometry, slicer nozzle mapping (vdpi 600..50), protocol/CRC, sender (retransmit, BUSY wait, stale ACK, bounded drain),
  serial link (EOF, write timeout, resync speed), filter (aspect, margins, alpha, 16-bit, non-square dpi), CUPS filter/backend logic and exit codes,
  PPD structure and mime types, and end-to-end tests.
- **Firmware, C99 with -Wall -Wextra -Werror and ASan+UBSan:** scheduler, parser, job controller, matrix head, motion, feed, maintenance FSM (unit tests);
  a coherent-sequence fuzzer (300k iterations, thousands of complete passes); 32 single-line mutants of the firmware, all killed (`tools_mutate.py`).
- **Full-pipeline simulator (`firmware/tests/sim.c`):** host filter -> frames -> the REAL C parser/job/scheduler/matrix driver -> simulated
  carriage, paper feed (fractional steps) and head -> printed page bitmap equals the input bitmap exactly, over a clean link, over a link
  with injected CRC errors and truncated frames, and through a pty via the real backend code.
- **CAD:** every part builds as one valid solid within the 220 mm bed; hole centres, radii, edge distance (>= 2 mm) and wall between holes
  (>= 1.2 mm) are asserted from the built geometry; bearing seat depth 7 mm with 3 mm floor and a shaft path; assembly numbers
  (stroke 248 mm needed vs 290 mm available on a 350 mm rail; 17 rail holes; 50.9 steps/mm feed).

## What the simulator does NOT prove (self-consistency only)
- The nozzle-to-(address,primitive) map in `sim.c` is a PLACEHOLDER, not HP45 wiring. The test proves the pipeline is consistent with itself.
- Ink flight is modelled as a constant integer lag in encoder counts; the bidirectional offset (= 2 x lag) is derived from that same model,
  so the bidirectional test proves the firmware implements the model, not that real drops behave that way.
- Motors are ideal; no electrical, thermal, or ink behaviour is simulated. The simulator runs each pass synchronously, so BUSY is unit-tested in C
  and in the Python sender, but not exercised in the pty/pipe end-to-end runs.

## Independent review and fixes (subagents + /code-review; every finding reproduced first)
- Round 1: parser init/reset, sender ACK matching (CRC echo), halftone speed, alpha, aspect, non-square dpi, nozzle divisibility, 16-bit greyscale,
  scheduler dir==0 hang, int32 overflow, config validation.
- Round 2: job controller (swath index reuse ignored; new header discarded an ACKed pass; no BUSY/back-pressure), motion overflows and slow sqrt,
  feed truncation/zero steps-per-mm, maintenance FAULT latch (now BUSY + `oi_maint_clear_fault`), CAD hole coordinates (chained workplane bug,
  vacuous assembly check), CUPS exit codes (retry is 6, not 1), DEVICE_URI traversal/symlink/non-tty handling, invalid PPD mime type, unbounded
  stale-reply loop, link EOF/write timeout/quadratic resync, unreachable entry points, stale docs.

## Sourced but NOT verified (search snippets; primary pages blocked in the sandbox)
- HP45: 300 nozzles/600 npi, 12.7 mm swath, 12 V, 52 contacts, 18 kHz max, 300 dpi recommended: confirmed by independent search summaries (ytec3d.com blocked).
  22 address lines x 14 primitives (300 of 308 slots used) comes from a patent snippet; exact nozzle mapping unknown.
- HP45 ~30 ohm heater and ~2 us pulse: UNVERIFIED. Measure on the bench.
- MGN9H carriage 20 x 40 x 8 mm, M3 holes 15 x 16 mm (vendor snippets; datasheet unreachable); rail hole pitch/edge are GUESS. Measure before printing.
- CUPS exit codes checked against OpenPrinting/cups backend.h; the filter/backend argv conventions, discovery line format and PPD keyword rules are from
  memory (no CUPS, `cupstestppd` not available here).
- SPDX IDs valid (list v3.29.0). Mixed per-folder licensing under an Apache-2.0 root is standard; a REUSE layout (SPDX headers, LICENSES/) is TODO;
  GPL/Apache compatibility not verified from a source; no legal review.

## Not built / not tested (needs hardware or a real CUPS)
- Physical printer, printhead pinout and firing electronics, motion/encoder hardware, paper path, ink behaviour, print quality, capping in practice.
- Device application on the MCU: main loop wiring `oi_job` -> maintenance -> motion -> scheduler -> head, step/dir drivers, encoder ISR, USB CDC (the core
  modules and their contracts exist and are tested; the board-specific glue does not).
- CUPS integration on a real CUPS install; PDF / cups-raster input route; job options (copies, resolution) are ignored.
- Parser mid-frame self-healing: relies on transport timeout + `oi_parser_reset` + ACK/retransmit (implemented in sim.c and sender.py).
