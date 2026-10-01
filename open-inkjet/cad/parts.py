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
    riser = cq.Workplane("XY").box(w, RISER_T, riser_h).translate((0, y_edge - RISER_T / 2, top - riser_h / 2))
    shelf_bot = top - riser_h
    shelf = cq.Workplane("XY").box(w, SHELF_LEN + RISER_T, SHELF_T).translate(
        (0, y_edge - RISER_T + (SHELF_LEN + RISER_T) / 2, shelf_bot + SHELF_T / 2))
    body = plate.union(riser).union(shelf)
    hy = y_edge + SHELF_LEN / 2
    for sx in (-1, 1):
        body = body.cut(_cyl(sx * HOLDER_HOLE_X, hy, 3.4, shelf_bot - 1, shelf_bot + SHELF_T + 1))
    return body


def platen_half():
    d = PLATEN_HALF
    p = cq.Workplane("XY").box(d["l"], d["w"], d["t"])
    lip = cq.Workplane("XY").box(d["l"], 2.0, PLATEN_LIP).translate((0, d["w"] / 2 - 1.0, d["t"] / 2 + PLATEN_LIP / 2))
    p = p.union(lip)
    for sx in (-1, 1):                                            # two mounting holes near the ends, clear of the lip
        p = p.cut(_cyl(sx * (d["l"] / 2 - 15), -8.0, 3.4, -d["t"], d["t"] * 2))
    return p


def sensor_mount():
    p = cq.Workplane("XY").box(30.0, 14.0, 4.0)
    for sx in (-1, 1):
        p = p.cut(_cyl(sx * SENSOR_HOLE_PITCH / 2, 0, 3.4, -4, 4))
    return p


def motor_mount():
    n = NEMA17; f = 50.0
    p = cq.Workplane("XY").box(f, f, MOTOR_PLATE_T)
    p = p.cut(_cyl(0, 0, n["pilot"] + PILOT_CLEAR, -MOTOR_PLATE_T, MOTOR_PLATE_T))          # pilot boss clearance
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = p.cut(_cyl(sx * n["hole_pitch"] / 2, sy * n["hole_pitch"] / 2, n["hole_d"], -MOTOR_PLATE_T, MOTOR_PLATE_T))
    return p


def encoder_bracket():
    p = cq.Workplane("XY").box(25.0, 16.0, 3.0)
    for sx in (-1, 1):
        p = p.cut(_cyl(sx * ENCODER_HOLE_PITCH / 2, 0, 3.4, -3, 3))
    return p


PARTS = dict(side_plate=side_plate, cartridge_holder=cartridge_holder, roller_block=roller_block,
             cap_base=cap_base, carriage_bracket=carriage_bracket, platen_half=platen_half, sensor_mount=sensor_mount,
             motor_mount=motor_mount, encoder_bracket=encoder_bracket)
