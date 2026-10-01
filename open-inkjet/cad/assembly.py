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
    holder_h = HP45_BOX["h"] + HOLDER_RIM_T                   # sleeve = cartridge + floor rim
    holder_bottom = nozzle_z - HOLDER_RIM_T                   # the cartridge rests on the rim, so its nozzle face is HOLDER_RIM_T above
    shelf_bottom = holder_bottom + holder_h                   # holder top meets the shelf underside
    riser_h = plate_top - shelf_bottom
    return dict(paper_top=paper_top, nozzle_z=nozzle_z, block_top=block_top, plate_top=plate_top,
                holder_bottom=holder_bottom, shelf_bottom=shelf_bottom, riser_h=riser_h)


def bracket_layout():
    """Machine Y positions (front = negative Y). The rail is on the rear extrusion (Y = EXT_HOLES[1][0]); the bracket's top
    plate is centred on it with its short side (the block width plus margins) across the rail; the riser is at its front edge
    and the shelf extends forward from there. Platen: starts one roller radius plus 2 mm in front of the roller axis (Y = 0)."""
    ext_y = EXT_HOLES[1][0]
    across = MGN9H["width"] + 2 * PLATE_MARGIN
    front_plate = ext_y - across / 2
    shelf_front = front_plate - RISER_T - SHELF_LEN                  # riser occupies [front_plate - RISER_T, front_plate]
    holder_c = front_plate - RISER_T - SHELF_LEN / 2
    platen_y0 = ROLLER_D / 2 + 2.0
    return dict(ext_y=ext_y, front_plate=front_plate, shelf_front=shelf_front, ext_front=ext_y - EXT_SIZE / 2,
                holder_y=(holder_c - 51 / 2, holder_c + 51 / 2),                # holder footprint is 51 mm long (45 + 2 x 3 wall)
                cartridge_y=(holder_c - HP45_BOX["l"] / 2, holder_c + HP45_BOX["l"] / 2),
                platen_y=(platen_y0, platen_y0 + PLATEN_HALF["w"]), roller_y=(-ROLLER_D / 2, ROLLER_D / 2),
                lip_y=(platen_y0 + PLATEN_HALF["w"] - 2.0, platen_y0 + PLATEN_HALF["w"]))


def post_layout():
    """Platen support posts: stem Y range (machine) and heights, compared with everything the carriage drags through that region."""
    ly = bracket_layout(); st = stack()
    ext_bottom = EXT_HOLES[0][1] - EXT_SIZE / 2
    platen_bottom = st["paper_top"] - PLATEN_HALF["t"]
    stem_y = (ly["ext_front"], ly["ext_front"] + POST_STEM_Y)
    return dict(ext_bottom=ext_bottom, platen_bottom=platen_bottom, foot_bottom=platen_bottom - POST_FOOT_T,
                stem_y=stem_y, stem_len=ext_bottom - POST_FLANGE_T - (platen_bottom - POST_FOOT_T),
                clear_to_carriage=stem_y[0] - ly["front_plate"],               # riser / shelf end at the plate's front edge
                foot_y=(ly["platen_y"][0], ly["platen_y"][1]))


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
    out["riser_clears_extrusion_mm"] = ly["ext_front"] - ly["front_plate"]       # riser sits at the plate's front edge, in front of the extrusion face
    out["holder_clearance_to_paper_mm"] = st["holder_bottom"] - st["paper_top"]
    out["holder_inside_shelf"] = ly["shelf_front"] <= ly["holder_y"][0] and ly["holder_y"][1] <= ly["front_plate"] - RISER_T
    out["cartridge_supported"] = ly["roller_y"][0] <= ly["cartridge_y"][0] and ly["cartridge_y"][1] <= ly["lip_y"][0] - 3.0
    out["cartridge_over_roller_mm"] = max(0.0, ly["roller_y"][1] - ly["cartridge_y"][0])
    pl = post_layout()
    out["post_clears_carriage_mm"] = pl["clear_to_carriage"]
    out["post_foot_clear_of_roller_mm"] = pl["foot_y"][0] - ly["roller_y"][1]
    out["platen_spans_plates"] = 2 * PLATEN_HALF["l"] >= PLATE_INNER_SPACING - 1e-9
    out["post_stem_len_mm"] = pl["stem_len"]
    out["nozzle_gap_mm"] = st["nozzle_z"] - st["paper_top"]
    return out


if __name__ == "__main__":
    for k, v in checks().items():
        print(k, v)
