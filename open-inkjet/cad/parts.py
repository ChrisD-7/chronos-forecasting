"""Printable frame parts (CadQuery). Every dimension comes from params.py; see the VERIFIED/GUESS tags there."""
import cadquery as cq
from params import *


def side_plate():
    sp = SIDE_PLATE
    p = cq.Workplane("XY").box(sp["w"], sp["h"], sp["t"])
    # rail mounting slots on the upper edge, 2 holes at RAIL_HOLE_PITCH
    p = p.faces(">Z").workplane().center(0, sp["h"] / 2 - 15).pushPoints(
        [(-RAIL_HOLE_PITCH / 2, 0), (RAIL_HOLE_PITCH / 2, 0)]).hole(RAIL_HOLE_D)
    # two 2020-extrusion cross-member bolt holes (M5, 5.5) and a 608 bearing seat for the feed roller
    p = p.faces(">Z").workplane().pushPoints([(-sp["w"] / 2 + 15, -sp["h"] / 2 + 15), (sp["w"] / 2 - 15, -sp["h"] / 2 + 15)]).hole(5.5)
    p = p.faces(">Z").workplane().center(0, -10).hole(BEARING_608["od"], BEARING_608["w"])
    return p


def cartridge_holder():
    b = HP45_BOX; wall = 3.0
    outer = cq.Workplane("XY").box(b["w"] + 2 * wall, b["l"] + 2 * wall, b["h"] * 0.5)
    pocket = cq.Workplane("XY").box(b["w"], b["l"], b["h"] * 0.5).translate((0, 0, wall))
    return outer.cut(pocket)


def roller_block():
    bb = BEARING_608
    blk = cq.Workplane("XY").box(bb["od"] + 12, bb["od"] + 12, bb["w"] + 4)
    return blk.faces(">Z").workplane().hole(bb["od"], bb["w"])


def cap_base():
    return (cq.Workplane("XY").box(30, 24, 6)
            .faces(">Z").workplane().rect(20, 14).cutBlind(-3))


PARTS = dict(side_plate=side_plate, cartridge_holder=cartridge_holder, roller_block=roller_block,
             cap_base=cap_base)
