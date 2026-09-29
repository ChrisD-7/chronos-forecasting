"""Shared CAD parameters. Every value is tagged VERIFIED (measured/datasheet read by us),
SOURCED (from a public page we could only see as a search snippet) or GUESS (to be measured)."""
BED_MM = 220.0            # printable bed limit we design to (Ender-3 class)

# MGN9H carriage block. SOURCED (vendor snippet, hta3d.com / robotdigg): body ~20 x 40 x 8 mm,
# M3 holes ~15 x 16 mm. NOT confirmed against a datasheet (dold-mechatronik PDF was unreachable).
MGN9H = dict(width=20.0, length=40.0, bolt_x=15.0, bolt_y=16.0, bolt_d=3.0)  # SOURCED

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
