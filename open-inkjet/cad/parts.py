"""Printable frame parts (CadQuery). Every dimension comes from params.py; see the VERIFIED/GUESS tags there.
Holes are cut with explicit absolute coordinates (no chained workplane offsets)."""
import cadquery as cq
from params import *


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
    return p


def cartridge_holder():
    b = HP45_BOX; wall = 3.0; hh = b["h"] * 0.5
    body = cq.Workplane("XY").box(b["w"] + 2 * wall, b["l"] + 2 * wall, hh)
    pocket = cq.Workplane("XY").box(b["w"], b["l"], hh).translate((0, 0, wall))
    body = body.cut(pocket)
    fl_x = HOLDER_HOLE_X + HOLDER_FLANGE_W / 2 - 1.7             # flange out to hole centre + 1.7 + edge
    for sx in (-1, 1):
        flange = cq.Workplane("XY").box(HOLDER_FLANGE_W + 4, 12.0, 3.0).translate(
            (sx * (HOLDER_HOLE_X + 0.0), 0, -hh / 2 + 1.5))
        body = body.union(flange)
        body = body.cut(_cyl(sx * HOLDER_HOLE_X, 0, 3.4, -hh, hh))
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


PARTS = dict(side_plate=side_plate, cartridge_holder=cartridge_holder, roller_block=roller_block,
             cap_base=cap_base)
