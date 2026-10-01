# Verification log (2026-09-29, build sandbox). Reproduce with `./run_tests.sh --mutate`.

## Tested by running code
- **Device application core (`firmware/core/oi_app.c`)**, run inside the simulator through a simulated HAL: uncap once per page, spit before printing, wipe after
  the page (`wipe_every_pages`), never fire while capped (`capped_fire=0`), carriage speed clamped to the head fire-rate limit, head re-capped after the idle
  timeout, and two pages in one job (swath indices restart at 0 and print again).
- **Board firmware (`firmware/board/rp2040`): COMPILED, NOT RUN.** Built against Pico SDK 2.3.1 with arm-none-eabi-gcc 13.2.1 and `-Wall -Wextra -Werror` on our sources:
  0 warnings, 37 KB text (dry variant); the armed variant (synthetic map compiled in) also builds. The pulse routine is in RAM and its disassembly shows the intended
  41-iteration settle loop, 83-iteration pulse loop and an interrupt mask around the pulse. Nothing about real timing, encoder decoding, servo angles, USB throughput or
  dual-core behaviour has been observed on a board. An independent review (reading the SDK sources) found and I fixed: negative-delay ramp bug (carriage would never
  accelerate; `drive(0)` would hang), restart race, pulse loop 3x too long, GPIO init glitch on OE_N/enables, `pass_ready`/`busy` hand-off order, missing homing, braking
  started too late.
- **Electronics (`electronics/`, 23 tests):** budget arithmetic checked by hand and by an independent reviewer; Pico SDK SPI baud algorithm reproduced (and the 25 MHz assumption
  corrected); block netlist with pin kinds and 13 injected defects all caught; simulated 74HC595 chain proves the firmware bit order reaches the intended head lines; `board_config.h`
  pins equal the netlist. This is a consistency model, not a circuit.
- **CUPS (real CUPS 2.4.7, `host/tests/cups_integration.py`, run with `./run_tests.sh --cups` as root):** `cupstestppd` on the PPD = PASS; a PNG submitted with `lp` went through
  cupsd, `oi_filter` and the `openinkjet` backend over a pty into the C firmware simulator and the printed page equalled the expected bitmap (24 swaths, no NAKs). Covers the direct
  image route only.
- **CAD (50 tests total, incl. a full 3D assembly):** 16 parts placed in machine coordinates with a pairwise boolean interference check at five carriage positions (including over the
  platen posts), plus deliberate-defect tests proving the check can fail. Dimensions are still GUESS values, so this shows the parts are consistent with each other, not that they fit real components.
- **(earlier) CAD additions (33 tests total):** carriage bracket (riser + shelf, height derived from the roller and rail stack), full-height cartridge holder with nozzle window and floor rim,
  platen halves, motor mount matching the NEMA 17 flange (sourced dims), sensor and encoder brackets; coordinates, edge distances, single-solid checks and a boolean check that the
  placeholder cartridge fits the holder without interference. The vertical stack and Y layout are arithmetic on GUESS dimensions, not a full 3D assembly.
- **Application-core unit tests (`firmware/tests/test_app.c`, scripted fake HAL):** action order over two pages, BUSY answered from an emulated ISR
  mid-pass, ramp must fit BOTH run-in distances (lead and tail, including the exact boundary), missed columns and stalled/backwards encoder reported to the
  host (`T_ERROR`) instead of silently dropped, positioning move before a pass when column counts differ, aborted job capped after `page_timeout_ms`,
  speed clamp, paper-step accounting, config/int32-range errors, FAULT recovery.
- **Host, 45 pytest tests:** geometry, slicer nozzle mapping (vdpi 600..50), protocol/CRC, sender (retransmit, BUSY wait, stale ACK, bounded drain),
  serial link (EOF, write timeout, resync speed), filter (aspect, margins, alpha, 16-bit, non-square dpi), CUPS filter/backend logic and exit codes,
  PPD structure and mime types, and end-to-end tests.
- **Firmware, C99 with -Wall -Wextra -Werror and ASan+UBSan:** scheduler, parser, job controller, matrix head, motion, feed, maintenance FSM (unit tests);
  a coherent-sequence fuzzer (300k iterations, thousands of complete passes); 53 single-line mutants of the firmware (including the application core), all killed and none invalid (`tools_mutate.py`).
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

- Round 4 (board firmware, electronics, CAD additions; two subagent reviews): see the per-section notes above. All findings reproduced or demonstrated before fixing.
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
- Board glue behaviour on real hardware: it compiles (above) but has never run. The feed/service split is unit-tested single-threaded only; true two-core concurrency,
  USB CDC throughput and the reply mutex are untested. The carriage motion is open-loop step generation with encoder feedback only for position (steps per count is a GUESS).
- Analog head-driver stage, schematic and PCB (docs/ELECTRONICS.md). Power-up procedure must follow docs/BENCH.md; wrong pulse parameters can destroy a head.
- Paper handling: no sheet loading, eject or paper-detect logic in firmware (pin reserved); the simulator treats "move to page" as a fresh sheet. Platen support posts, motor bolt pattern
  and sensor/encoder slot bolts are now designed in CAD (consistency-checked only). CAD orientation of cartridge/holder/shelf relative to the paper feed is OPEN until the cartridge is measured.
- Carriage orientation (rail along machine X, block length along X, bolt pattern 16 along / 15 across: a GUESS), rail/block dimensions and the motor-to-roller coupling (a purchased flexible
  5 mm to 8 mm coupler is assumed; the standoff and coupler length are not designed) are unverified. The rail, block, belt, motors and fasteners are not in the 3D model.
- CUPS: PDF / cups-raster input route (documents from desktop apps), job options (copies, resolution, orientation), other CUPS versions, running the filter under a locked-down `lp` user / AppArmor/SELinux profiles.
- Parser mid-frame self-healing: relies on transport timeout + `oi_parser_reset` + ACK/retransmit (implemented in sim.c and sender.py).
