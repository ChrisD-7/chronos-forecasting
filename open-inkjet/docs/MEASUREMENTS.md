# Measurements log (empty until hardware exists)
Fill each row from a caliper / scope / ruler measurement, then update the tagged constant. Do not enter values from datasheets here.

| Quantity | Value | Method / date | Updates |
|---|---|---|---|
| HP45 cartridge outline (w x l x h) | | caliper | cad/params.py HP45_BOX |
| HP45 nozzle map (300 entries) | | continuity per docs/BENCH.md | firmware nozzle_map[] passed to oi_matrix_head_init |
| HP45 heater resistance / fire pulse | | ohmmeter, scope | docs/VERIFICATION.md (currently UNVERIFIED) |
| MGN9H carriage body, bolt pattern, thread depth | | caliper | cad/params.py MGN9H |
| Rail hole pitch / edge distance | | caliper | RAIL_HOLE_PITCH, RAIL_EDGE |
| Encoder counts per mm | | 200 mm travel | firmware counts_per_dot |
| Forward/reverse dot offset | | printed test | firmware bidir_offset_counts (sim: = 2 x lag) |
| Feed steps/mm, cumulative error | | 10 swaths, ruler | oi_feed_init steps_per_mm_x1000 |
| Unprintable border | | print + measure | host/openinkjet/filter.py MARGIN_MM and PPD ImageableArea |
