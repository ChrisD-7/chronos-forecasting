"""Shared CAD parameters. Every value is tagged VERIFIED (measured/datasheet read by us),
SOURCED (from a public page we could only see as a search snippet) or GUESS (to be measured)."""
BED_MM = 220.0            # printable bed limit we design to (Ender-3 class)

# MGN9H carriage block. SOURCED (vendor snippet, hta3d.com / robotdigg): body ~20 x 40 x 8 mm,
# M3 holes ~15 x 16 mm. NOT confirmed against a datasheet (dold-mechatronik PDF was unreachable).
MGN9H = dict(width=20.0, length=40.0, bolt_x=15.0, bolt_y=16.0, bolt_d=3.0)  # SOURCED

PLATE_T = 4.0             # GUESS: adapter plate thickness
PLATE_MARGIN = 6.0        # GUESS
