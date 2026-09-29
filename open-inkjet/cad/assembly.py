# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Assembly-level consistency checks that need no CAD kernel: numbers that must agree across parts."""
import math
from params import *


def required_stroke():
    """Carriage travel needed: page + margins + park zone (capping/wiping)."""
    return PAGE_W + 2 * PAGE_MARGIN + PARK_ZONE


def available_stroke():
    """Carriage-block travel on the rail after subtracting the block and end-stop room."""
    return RAIL_LEN - CARRIAGE_BODY_W - 2 * STOP_MARGIN


def rail_holes():
    n = int((RAIL_LEN - 2 * RAIL_EDGE) // RAIL_HOLE_PITCH) + 1
    return [RAIL_EDGE + i * RAIL_HOLE_PITCH for i in range(n)]


def feed_steps_per_mm():
    return MOTOR_FULL_STEPS * MICROSTEPS / (math.pi * ROLLER_D)     # roller drive, no gearing


def stack():
    """Vertical layout (machine Z, mm) derived from the rail, roller and cartridge parameters. The paper plane is fixed by
    the feed roller (seat centre from the side plate) and everything above it is derived, so a flat plate on the carriage
    block could not reach the paper: the bracket needs a riser and a shelf."""
    seat_z = -20.0                                            # parts.side_plate: bearing seat / roller axis height
    ext_z = EXT_HOLES[0][1]                                   # extrusion centre height (side plate hole y)
    paper_top = seat_z + ROLLER_D / 2
    nozzle_z = paper_top + NOZZLE_GAP
    block_top = ext_z + EXT_SIZE / 2 + MGN_H_TOTAL
    plate_top = block_top + PLATE_T
    shelf_bottom = nozzle_z + HP45_BOX["h"]                   # cartridge hangs below the shelf
    riser_h = plate_top - shelf_bottom
    return dict(paper_top=paper_top, nozzle_z=nozzle_z, block_top=block_top, plate_top=plate_top,
                shelf_bottom=shelf_bottom, riser_h=riser_h)


def bracket_layout():
    """Y positions (machine, front = negative Y). Rear extrusion centre = EXT_HOLES[1][0]; bracket top plate centred on it."""
    ext_y = EXT_HOLES[1][0]
    plate_len = MGN9H["length"] + 12.0
    front_plate = ext_y - plate_len / 2
    shelf_front = front_plate - SHELF_LEN
    return dict(ext_y=ext_y, front_plate=front_plate, shelf_front=shelf_front,
                ext_front=ext_y - EXT_SIZE / 2, holder_y_span=(shelf_front + (SHELF_LEN - 51) / 2, front_plate - (SHELF_LEN - 51) / 2))


def checks():
    out = {}
    out["required_stroke_mm"] = required_stroke()
    out["available_stroke_mm"] = available_stroke()
    out["stroke_slack_mm"] = available_stroke() - required_stroke()
    out["rail_holes"] = len(rail_holes())
    out["backing_extrusion_len_mm"] = RAIL_LEN                       # rail is bolted along its full length
    out["side_plate_inner_spacing_mm"] = PLATE_INNER_SPACING
    out["rail_fits_between_plates"] = RAIL_LEN <= PLATE_INNER_SPACING
    out["feed_steps_per_mm"] = feed_steps_per_mm()
    st, ly = stack(), bracket_layout()
    out.update({"stack_" + k: v for k, v in st.items()})
    out["riser_positive"] = st["riser_h"] > 0
    out["shelf_clears_extrusion_y"] = ly["front_plate"] - SHELF_LEN < ly["ext_front"] - 3.0     # shelf ends well in front of the extrusion
    out["nozzle_gap_mm"] = st["nozzle_z"] - st["paper_top"]
    return out


if __name__ == "__main__":
    for k, v in checks().items():
        print(k, v)
