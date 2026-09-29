# Verification log (2026-09-29, build sandbox). Reproduce with `./run_tests.sh --mutate`.

## Tested by running code
- **Device application core (`firmware/core/oi_app.c`)**, run inside the simulator through a simulated HAL: uncap once per page, spit before printing, wipe after
  the page (`wipe_every_pages`), never fire while capped (`capped_fire=0`), carriage speed clamped to the head fire-rate limit, head re-capped after the idle
  timeout, and two pages in one job (swath indices restart at 0 and print again).
- **Application-core unit tests (`firmware/tests/test_app.c`, scripted fake HAL):** action order over two pages, BUSY answered from an emulated ISR
  mid-pass, ramp must fit BOTH run-in distances (lead and tail, including the exact boundary), missed columns and stalled/backwards encoder reported to the
  host (`T_ERROR`) instead of silently dropped, positioning move before a pass when column counts differ, aborted job capped after `page_timeout_ms`,
  speed clamp, paper-step accounting, config/int32-range errors, FAULT recovery.
- **Host, 45 pytest tests:** geometry, slicer nozzle mapping (vdpi 600..50), protocol/CRC, sender (retransmit, BUSY wait, stale ACK, bounded drain),
  serial link (EOF, write timeout, resync speed), filter (aspect, margins, alpha, 16-bit, non-square dpi), CUPS filter/backend logic and exit codes,
  PPD structure and mime types, and end-to-end tests.
- **Firmware, C99 with -Wall -Wextra -Werror and ASan+UBSan:** scheduler, parser, job controller, matrix head, motion, feed, maintenance FSM (unit tests);
  a coherent-sequence fuzzer (300k iterations, thousands of complete passes); 45 single-line mutants of the firmware (including the application core), all killed and none invalid (`tools_mutate.py`).
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

- Round 3 (application core, reproduced by an independent scripted-HAL driver): passes dropped silently after START was ACKed (now a `T_ERROR` frame, host raises
  `DeviceError`); run-in margin checked against the wrong distance; carriage started a pass wherever the last one ended (columns lost; now a positioning move and
  a missed-column check); no watchdog on the carriage loop (`stall_ticks`); head never capped after an aborted job (`page_timeout_ms`); int32 overflow in
  column position math; FAULT was unrecoverable (`oi_maint_clear_fault`). Whole-project audit: README status reworded, SPDX headers + `REUSE.toml` +
  `NOTICE.md` + `docs/PROVENANCE.md` added.

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
- Board glue for a real MCU: the `oi_hal_t` implementation (step/dir generation with the planned trapezoid, encoder ISR/PIO, head GPIO timing, USB CDC).
  `oi_app.c` itself is board-independent and tested only against the simulated HAL.
- Known design limit: `oi_app_rx()` is polled and runs a whole pass before returning (see the comment in `oi_app.h`). On hardware, RX must be interrupt/DMA
  buffered and the host reply timeout must exceed a pass (or an ISR must answer BUSY); the simulator finishes passes in microseconds so this is not exercised.
- Paper eject/sheet loading is not modelled: the simulator treats "move to page" as a fresh sheet.
- CUPS integration on a real CUPS install; PDF / cups-raster input route; job options (copies, resolution) are ignored.
- Parser mid-frame self-healing: relies on transport timeout + `oi_parser_reset` + ACK/retransmit (implemented in sim.c and sender.py).
