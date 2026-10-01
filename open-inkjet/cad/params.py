# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Shared CAD parameters. Every value is tagged VERIFIED (measured/datasheet read by us),
SOURCED (from a public page we could only see as a search snippet) or GUESS (to be measured)."""
BED_MM = 220.0            # printable bed limit we design to (Ender-3 class)

# MGN9H carriage block. SOURCED (vendor snippet, hta3d.com / robotdigg): body ~20 x 40 x 8 mm,
# M3 holes ~15 x 16 mm. NOT confirmed against a datasheet (dold-mechatronik PDF was unreachable).
# bolt_across = hole spacing across the rail (plate y), bolt_along = along the rail (plate x). Vendor says "15 x 16"; which is which is a GUESS.
MGN9H = dict(width=20.0, length=40.0, bolt_across=15.0, bolt_along=16.0, bolt_d=3.0)  # SOURCED (weak)

PLATE_T = 4.0             # GUESS: adapter plate thickness
PLATE_MARGIN = 6.0        # GUESS

# ---- frame / paper path (all GUESS until the physical parts are measured; assembly.py checks consistency) ----
RAIL_LEN = 350.0          # stock MGN9 length (SOURCED: vendors list 150/300/350/400 mm); mounted on a same-length 2020 backing extrusion
RAIL_EDGE = 10.0          # GUESS: distance from rail end to first hole
PLATE_INNER_SPACING = 350.0   # distance between side plates = length of the 2020 backing extrusions
STOP_MARGIN = 10.0        # end stop / bumper / belt clamp room at each end of the rail
RAIL_HOLE_PITCH = 20.0    # GUESS (commonly 20 mm for MGN9; verify on the real rail)
RAIL_HOLE_D = 3.5         # GUESS
PAGE_W = 210.0            # A4 width (carriage axis)
PAGE_MARGIN = 4.0
CARRIAGE_BODY_W = 40.0    # carriage + cartridge holder footprint along the rail (GUESS)
PARK_ZONE = 30.0          # capping/wipe zone beyond the page
SIDE_PLATE = dict(w=180.0, h=150.0, t=10.0)         # GUESS
EXT_HOLES = ((-70.0, 50.0), (70.0, 50.0))            # M5 end-tap holes for the two 2020 extrusions (GUESS layout)
EXT_HOLE_D = 5.5
BEARING_SEAT_CLEAR = 0.3   # printed seat diameter = 608 OD + this (FDM fit)
SHAFT_D = 8.0
SHAFT_HOLE_D = 9.0
HOLDER_HOLE_X = 17.0      # M3 pattern shared by carriage_plate and cartridge_holder flanges (+/- x)
HOLDER_FLANGE_W = 8.0
MOTOR_FULL_STEPS = 200; MICROSTEPS = 16
# HP45 cartridge outline: NOT KNOWN, placeholder box to be replaced by a caliper measurement
HP45_BOX = dict(w=20.0, l=45.0, h=45.0)             # GUESS -- MEASURE
ROLLER_D = 20.0           # GUESS feed roller diameter
BEARING_608 = dict(od=22.0, id=8.0, w=7.0)          # 608 bearing, standard dimensions

# ---- paper path and carriage stack (added with the assembly model; GUESS unless tagged) ----
EXT_SIZE = 20.0            # 2020 extrusion (nominal 20 x 20 mm, standard)
MGN_H_TOTAL = 10.0         # GUESS: MGN9H rail bottom to block top (vendor listings say ~10 mm; measure)
NOZZLE_GAP = 2.0           # GUESS: printhead to paper distance (typical thermal inkjet 1-2 mm; keeps the holder rim >= 1 mm above the paper)
SHELF_T = 4.0
RISER_T = 4.0
SHELF_LEN = 55.0           # shelf depth beyond the top plate; must hold the 51 mm holder footprint
PLATEN_HALF = dict(l=175.0, w=46.0, t=6.0)     # two halves span the 350 mm between the side plates; each fits the 220 mm bed
PLATEN_LIP = 2.0           # paper-guide lip height
# NEMA 17 flange (SOURCED via search: 42.3 mm face, 31 mm hole spacing, 22 mm pilot, M3 holes: MOONS', RepRap wiki, jlcmc)
NEMA17 = dict(face=42.3, hole_pitch=31.0, pilot=22.0, hole_d=3.4)
MOTOR_PLATE_T = 6.0
SENSOR_HOLE_PITCH = 20.0   # GUESS: optical end-stop / paper sensor board
ENCODER_HOLE_PITCH = 12.0  # GUESS: encoder reader

HOLDER_RIM_T = 1.0         # floor rim that the cartridge rests on; the nozzle window is cut inside it
HOLDER_RIM_W = 2.0         # rim width around the nozzle window
HOLDER_WALL = 3.0
PILOT_CLEAR = 1.0          # extra diameter on the motor pilot bore (FDM tolerance; was 0.5, too tight)

# platen support posts: hang from the rear extrusion's bottom face, in front of nothing the carriage touches (see assembly.post_layout())
POST_FLANGE_T = 4.0
POST_STEM_Y = 6.0          # stem thickness in Y, flush with the extrusion's front face
POST_FOOT_T = 6.0
POST_X = (-130.0, 0.0, 130.0)   # 0.0 = the joint between the two platen halves (a post foot straddles it)
POST_W = 20.0
# motor mount to side plate: M3 square around the roller axis (GUESS; both parts use it)
MOTOR_BOLT_SQUARE = 21.0
M5_HOLE_D = 5.5

# bearing retainer: a thin ring between the side plate and the motor mount; its bore overlaps the 608 OUTER race only (inner ring OD about 12 mm)
RETAINER_T = 2.0
RETAINER_OD = 50.0
RETAINER_BORE = 16.0       # < 22 (bearing OD) so it retains; > 12 + clearance so it never touches the rotating inner ring (608 inner ring OD ~ 12, GUESS)
BEARING_INNER_RING_OD = 12.0
