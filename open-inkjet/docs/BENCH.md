# Bench bring-up procedures (what only hardware can verify)

Everything in software is simulated: `firmware/tests/sim.c` uses a PLACEHOLDER nozzle map, ideal motors and ink flight
modelled as a constant lag. These procedures replace those assumptions with measurements. Record results in
`docs/MEASUREMENTS.md` (create it) and fix the tagged values in `cad/params.py`, `host/openinkjet/heads.py`.

## Phase 2: HP45 printhead
1. Caliper the cartridge outline and contact pad pitch -> `cad/params.py: HP45_BOX`. Do not print holders before this.
2. Power only after continuity checks: with the cartridge OUT of the printer, measure resistance between each primitive
   pin and its common through each address (expect ~tens of ohms per heater; source only says ~30 ohm, UNVERIFIED).
   Fill `nozzle_map[300]` = (address << 8) | primitive from measurement; `oi_matrix_head_init` rejects duplicates/out-of-range.
3. Known public scheme (patent snippet via search): 22 address lines, 14 primitives + 14 commons, 300 resistors, one
   address enabled at a time. Confirm against your measurement, not vice versa.
4. Fire one nozzle into a cotton swab at low voltage first; scope the pulse: width ~ inks dependent; start short and
   increase until reliable ejection, then record the value. Never fire dry (heaters burn out).
5. Acceptance: a 300-nozzle test column prints 300 distinct dots on paper with the head held static; count them.

## Phase 3: carriage + encoder
1. Fit MGN9H to the printed side plates; check rail parallelism to the platen (dial gauge, target < 0.1 mm over 210 mm).
2. Measure encoder counts per mm over 200 mm travel; set `counts_per_dot` and confirm 2 counts/dot at 150 lpi quadrature.
3. Print a 1-dot vertical line at 3 x positions in each direction; measure the forward/reverse offset and set
   `bidir_offset_counts` (simulation says offset = 2 x ink-flight lag in counts).
4. Accept: line position error < 1/2 dot (42 um) across the page, both directions.

## Phase 4: paper feed
1. Mark 10 swaths on a sheet; measure with a ruler/scanner; adjust steps/mm (`oi_feed_init`) until cumulative error < 0.2 mm/297 mm.
2. Skew: print a full-width line, feed 250 mm, print another; measure parallelism.

## Phase 5/6: full page and maintenance
1. 300 dpi A4 test image through `oi_filter` -> USB serial -> printer; inspect banding at swath joins (feed error).
2. Tune spit count (`spit_before_pass`), wipe interval and idle-cap time; 50-page run with nozzle check before/after.
