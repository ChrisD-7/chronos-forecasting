# Draft BOM (v0, unpriced). Quantities follow cad/ and assembly.py; every part must be checked against the real
# dimensions (cad/params.py tags: GUESS / SOURCED) before ordering.
| Item | Qty | Note |
|---|---|---|
| MGN9H rail 350 mm + carriage block | 1 | 350 mm stock length is SOURCED (vendors list 150/300/350/400); alt MGN12H, benchmark both |
| 2020 aluminium extrusion, 350 mm | 2 | rear: rail backing (rail bolted along its full length, 17 holes at 20 mm pitch, GUESS pitch); front: platen/paper guide |
| M5 x 10-16 bolts + 2020 T-nuts / end-tap | 4 | side plate to extrusion ends (cad/parts.py EXT_HOLES) |
| M3 screws, nuts/nut traps | ~40 | 15 rail screws (length = rail counterbore + extrusion thread, measure), 4 carriage-to-plate, 2 holder, 2+ roller block, cap; none modelled as nut traps yet |
| Side plates (printed) | 2 | PETG/ASA, 180 x 150 x 10 mm, fits a 220 mm bed |
| Carriage plate, cartridge holder, roller block, cap base (printed) | 1 each (+1 roller block if idler) | holder pocket is a placeholder until HP45 is measured |
| 608 bearings | 2-4 | 2 in side-plate seats (+2 if a printed roller block is used as the idler side) |
| 8 mm shaft / feed roller (about 20 mm dia, GUESS) | 1 | passes through the plate shaft holes (9 mm) |
| NEMA17 stepper + driver, GT2 belt (~1 m, buy 1 m), GT2 idler pulley + belt clamps | 1 set | carriage drive; belt length ~2 x 350 mm plus wrap |
| Feed motor (NEMA17) + driver | 1 | 50.9 steps/mm at 20 mm roller, 16 microsteps (assembly.py); firmware takes steps/mm as a parameter |
| Linear optical encoder strip + reader | 1 | strip about 300 mm+ (buy 350) for the 290 mm carriage travel |
| End-stop switches | 2 | not modelled in CAD |
| Cap gasket (silicone) + wiper blade | 1 set | for cap_base and maintenance FSM |
| HP 45 (51645A) cartridge | 2+ | spare for bench damage |
| RP2040 board (Raspberry Pi Pico class; firmware builds for it) | 1 | board firmware compiles with Pico SDK 2.3.1; not run on hardware |
| 74HC595 shift registers | 5 | 40 outputs for 22 address + 14 primitive + 4 spare (electronics/design.py) |
| 12 V head driver stage: 22 address drivers + 14 high-current primitive switches, level shifting, fuse | 1 | analog stage NOT designed; needs measured head parameters (docs/ELECTRONICS.md) |
| Bulk capacitor: 470 uF or more, total ESR + wiring < 107 mohm (400 uF is the no-recharge bound; 18.7 uF is only the single-pulse minimum) | 1+ | 5.6 A / 2 us worst-case pulse; sized with electronics/spice_sim.py (design numbers use UNVERIFIED heater values) |
| Pogo-pin head connector, 52 contacts | 1 | contact pitch not measured |
| Hobby servos (cap, wiper) | 2 | actuation angles GUESS in board_config.h |
| Platen halves (175 mm), platen posts (1 joint + 2 outer), sensor mount, motor mount(s), encoder bracket, carriage bracket (printed) | 2 / 3 / 1 / 2 / 1 / 1 | cad/parts.py; NEMA17 flange dims sourced, others GUESS; M5 slot bolts on the posts, sensor and encoder brackets |
| M5 bolts + T-nuts for posts and brackets | 6 | 3 posts + sensor + encoder + spare |
| Motor-to-roller flexible shaft coupler (5 mm to 8 mm) | 1 | purchased part; standoff/length between motor mount and roller not designed |
| Pull-up (OE_N) and pull-down (36 driver inputs) resistors | 37 | netlist.py; values not chosen |
| Pi Zero 2 W (CUPS host) | 1 | |
| 12 V PSU, wiring, cartridge contact (pogo) board | 1 | |
| PETG/ASA filament | - | |
