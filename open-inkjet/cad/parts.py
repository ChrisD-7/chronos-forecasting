# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Printable frame parts (CadQuery). Every dimension comes from params.py; see the VERIFIED/GUESS tags there.
Holes are cut with explicit absolute coordinates (no chained workplane offsets)."""
import cadquery as cq
from params import *
import assembly, carriage_plate


def _cyl(x, y, d, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(d / 2).extrude(z1 - z0)


def side_plate():
    sp = SIDE_PLATE; t = sp["t"]
    p = cq.Workplane("XY").box(sp["w"], sp["h"], t)              # z in [-t/2, t/2]
    for (x, y) in EXT_HOLES:                                     # extrusion end-tap holes, through
        p = p.cut(_cyl(x, y, EXT_HOLE_D, -t, t))
    seat_d = BEARING_608["od"] + BEARING_SEAT_CLEAR
    p = p.cut(_cyl(0, -20, seat_d, t / 2 - BEARING_608["w"], t))          # blind seat from +Z face
    p = p.cut(_cyl(0, -20, SHAFT_HOLE_D, -t, t))                          # shaft passes through the floor
    for sx in (-1, 1):                                                    # motor mount bolts, square around the roller axis
        for sy in (-1, 1):
            p = p.cut(_cyl(sx * MOTOR_BOLT_SQUARE, -20 + sy * MOTOR_BOLT_SQUARE, 3.4, -t, t))
    return p


def holder_height():
    return HP45_BOX["h"] + HOLDER_RIM_T


def cartridge_holder():
    """Sleeve for the cartridge: full cartridge height plus a floor rim, with a nozzle window cut through the rim, and
    flanges at the TOP that bolt to the carriage shelf. The cartridge is inserted from the top before the holder is bolted
    under the shelf. Local frame: centred on the body, z in [-H/2, H/2]."""
    b = HP45_BOX; H = holder_height(); wall = HOLDER_WALL
    body = cq.Workplane("XY").box(b["w"] + 2 * wall, b["l"] + 2 * wall, H)
    pocket = cq.Workplane("XY").box(b["w"], b["l"], b["h"]).translate((0, 0, HOLDER_RIM_T / 2))      # spans [-H/2+rim, H/2]
    body = body.cut(pocket)
    window = cq.Workplane("XY").box(b["w"] - 2 * HOLDER_RIM_W, b["l"] - 2 * HOLDER_RIM_W, HOLDER_RIM_T + 2).translate((0, 0, -H / 2))
    body = body.cut(window)                                                                            # nozzle window through the rim
    for sx in (-1, 1):
        flange = cq.Workplane("XY").box(HOLDER_FLANGE_W + 4, 12.0, 3.0).translate(
            (sx * HOLDER_HOLE_X, 0, H / 2 - 1.5))                                                      # flanges at the TOP
        body = body.union(flange)
        body = body.cut(_cyl(sx * HOLDER_HOLE_X, 0, 3.4, -H, H))
    return body


def roller_block():
    bb = BEARING_608
    w = bb["od"] + BEARING_SEAT_CLEAR + 18.0                     # 40 mm
    h = bb["w"] + 4.0
    blk = cq.Workplane("XY").box(w, w, h)
    blk = blk.cut(_cyl(0, 0, bb["od"] + BEARING_SEAT_CLEAR, h / 2 - bb["w"], h))   # blind seat
    blk = blk.cut(_cyl(0, 0, SHAFT_HOLE_D, -h, h))                                  # shaft through-hole
    for sx in (-1, 1):
        blk = blk.cut(_cyl(sx * 16.0, 0, 3.4, -h, h))
    return blk


def cap_base():
    return (cq.Workplane("XY").box(30, 24, 6)
            .faces(">Z").workplane().rect(20, 14).cutBlind(-3))


def carriage_bracket():
    """Top plate (bolts to the MGN9H block) + riser + shelf carrying the cartridge holder down to the paper.
    Local frame: x along the rail, +y toward the front of the printer, z up; plate spans z in [-t/2, t/2]."""
    plate = carriage_plate.build(holder_holes=())          # the holder bolts to the shelf, not to the top plate
    bb = plate.val().BoundingBox()
    st = assembly.stack()
    riser_h = st["riser_h"]
    top = PLATE_T / 2
    w, y_edge = bb.xlen, bb.ylen / 2
    riser = cq.Workplane("XY").box(w, RISER_T, riser_h).translate((0, y_edge + RISER_T / 2, top - riser_h / 2))      # OUTSIDE the plate's front edge
    shelf_bot = top - riser_h
    shelf = cq.Workplane("XY").box(w, SHELF_LEN + RISER_T, SHELF_T).translate(
        (0, y_edge + (SHELF_LEN + RISER_T) / 2, shelf_bot + SHELF_T / 2))
    body = plate.union(riser).union(shelf)
    hy = y_edge + RISER_T + SHELF_LEN / 2
    for sx in (-1, 1):
        body = body.cut(_cyl(sx * HOLDER_HOLE_X, hy, 3.4, shelf_bot - 1, shelf_bot + SHELF_T + 1))
    return body


def platen_half(side=-1):
    """side = -1 for the half at negative X (joint at its +x end), +1 for the other. Holes line up with the post feet:
    one 5 mm from the joint end, one over the outer post (local x = -side*... see platen_hole_xs())."""
    d = PLATEN_HALF
    p = cq.Workplane("XY").box(d["l"], d["w"], d["t"])
    lip = cq.Workplane("XY").box(d["l"], 2.0, PLATEN_LIP).translate((0, d["w"] / 2 - 1.0, d["t"] / 2 + PLATEN_LIP / 2))
    p = p.union(lip)
    for hx in platen_hole_xs(side):
        p = p.cut(_cyl(hx, -8.0, 3.4, -d["t"], d["t"] * 2))
    return p


def platen_hole_xs(side=-1):
    """Hole x positions in the half's own frame (centre of the half = 0). Half centre sits at machine X = side * l/2."""
    d = PLATEN_HALF
    centre = side * d["l"] / 2
    joint_hole = -side * (d["l"] / 2 - 5.0)              # 5 mm from the joint end (the post foot straddles the joint)
    outer_post = side * POST_X[2] if side > 0 else side * abs(POST_X[0])
    outer_hole = outer_post - centre
    return [joint_hole, outer_hole]


def platen_post(joint=False):
    """Support post: top flange bolts to the extrusion bottom face (M5 into a T-nut), stem drops in front of nothing, foot carries the platen.
    Local frame: x along the printer, y = machine Y - ext_y (flange centred on 0), z = machine Z - extrusion bottom (flange below 0)."""
    st = assembly.stack(); ext_bottom = EXT_HOLES[0][1] - EXT_SIZE / 2
    platen_bottom = st["paper_top"] - PLATEN_HALF["t"]
    foot_top = platen_bottom - ext_bottom                         # local z of the platen underside
    foot_bot = foot_top - POST_FOOT_T
    flange = cq.Workplane("XY").box(POST_W, EXT_SIZE, POST_FLANGE_T).translate((0, 0, -POST_FLANGE_T / 2))
    stem_h = -POST_FLANGE_T - foot_bot
    stem = cq.Workplane("XY").box(POST_W, POST_STEM_Y, stem_h).translate((0, -EXT_SIZE / 2 + POST_STEM_Y / 2, -POST_FLANGE_T - stem_h / 2))
    ly = assembly.bracket_layout()
    y0, y1 = ly["platen_y"][0] - ly["ext_y"], ly["platen_y"][1] - ly["ext_y"]      # platen span in local y
    y1 = -EXT_SIZE / 2 + POST_STEM_Y                                              # foot runs back to the stem's rear face (it must join it)
    foot = cq.Workplane("XY").box(POST_W, y1 - y0, POST_FOOT_T).translate((0, (y0 + y1) / 2, (foot_top + foot_bot) / 2))
    body = flange.union(stem).union(foot)
    body = body.cut(_cyl(0, 0, M5_HOLE_D, -POST_FLANGE_T - 1, 1))                   # M5 through the flange, over the T-slot centre
    hy = ly["platen_y"][0] + PLATEN_HALF["w"] / 2 - 8.0 - ly["ext_y"]                # machine Y of the platen holes, local
    for hx in ([-5.0, 5.0] if joint else [0.0]):
        body = body.cut(_cyl(hx, hy, 3.4, foot_bot - 1, foot_top + 1))
    return body


def sensor_mount():
    """Board holes (M3, pitch GUESS) plus an M5 hole to the extrusion T-slot."""
    p = cq.Workplane("XY").box(30.0, 26.0, 4.0)
    for sx in (-1, 1):
        p = p.cut(_cyl(sx * SENSOR_HOLE_PITCH / 2, -6.0, 3.4, -4, 4))
    return p.cut(_cyl(0, 6.0, M5_HOLE_D, -4, 4))


def motor_mount():
    n = NEMA17; f = 50.0
    p = cq.Workplane("XY").box(f, f, MOTOR_PLATE_T)
    p = p.cut(_cyl(0, 0, n["pilot"] + PILOT_CLEAR, -MOTOR_PLATE_T, MOTOR_PLATE_T))          # pilot boss clearance
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = p.cut(_cyl(sx * n["hole_pitch"] / 2, sy * n["hole_pitch"] / 2, n["hole_d"], -MOTOR_PLATE_T, MOTOR_PLATE_T))
    for sx in (-1, 1):                                    # bolts to the side plate: same square as parts.side_plate around the roller axis
        for sy in (-1, 1):
            p = p.cut(_cyl(sx * MOTOR_BOLT_SQUARE, sy * MOTOR_BOLT_SQUARE, 3.4, -MOTOR_PLATE_T, MOTOR_PLATE_T))
    return p


def bearing_retainer():
    """Ring between the side plate's outer face and the motor mount: holds the 608 bearing in its seat. Same M3 square as the motor mount."""
    r = cq.Workplane("XY").box(RETAINER_OD, RETAINER_OD, RETAINER_T)
    r = r.cut(_cyl(0, 0, RETAINER_BORE, -RETAINER_T, RETAINER_T))
    for sx in (-1, 1):
        for sy in (-1, 1):
            r = r.cut(_cyl(sx * MOTOR_BOLT_SQUARE, sy * MOTOR_BOLT_SQUARE, 3.4, -RETAINER_T, RETAINER_T))
    return r


def encoder_bracket():
    """Reader holes (M3, pitch GUESS) plus an M5 hole to the extrusion T-slot. The encoder strip slot is not designed."""
    p = cq.Workplane("XY").box(25.0, 28.0, 3.0)
    for sx in (-1, 1):
        p = p.cut(_cyl(sx * ENCODER_HOLE_PITCH / 2, -8.0, 3.4, -3, 3))
    return p.cut(_cyl(0, 8.0, M5_HOLE_D, -3, 3))


PARTS = dict(side_plate=side_plate, cartridge_holder=cartridge_holder, roller_block=roller_block,
             cap_base=cap_base, carriage_bracket=carriage_bracket, platen_half=platen_half, platen_half_right=lambda: platen_half(+1),
             platen_post_outer=platen_post, platen_post_joint=lambda: platen_post(joint=True), sensor_mount=sensor_mount,
             motor_mount=motor_mount, encoder_bracket=encoder_bracket, bearing_retainer=bearing_retainer)
