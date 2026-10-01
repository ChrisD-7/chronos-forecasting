# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Full 3D assembly in machine coordinates (X along the rail, Y depth with the front at -Y, Z up) and a pairwise boolean
interference check. Dimensions are the GUESS values from params.py, so this proves the parts are consistent with each other, not
that they fit real components. Rail, carriage block, belt, motors and fasteners are not modelled."""
import itertools
import cadquery as cq
from params import *
import assembly
import parts


def _place(wp, x=0.0, y=0.0, z=0.0, rot_z=0):
    s = wp.val()
    if rot_z:
        s = s.rotate((0, 0, 0), (0, 0, 1), rot_z)
    return s.translate(cq.Vector(x, y, z))


def side_plate_placed(sign):
    """Plate local (x, y, z) -> machine (Y, Z, X) (a 120 degree turn about (1,1,1)); the seat opens outward (+X for sign=+1)."""
    s = parts.side_plate().val().rotate((0, 0, 0), (1, 1, 1), 120)
    if sign < 0:
        s = s.rotate((0, 0, 0), (0, 0, 1), 180)           # the plate is symmetric in local x, so a 180 degree turn about Z is a mirror here
    return s.translate(cq.Vector(sign * (PLATE_INNER_SPACING / 2 + SIDE_PLATE["t"] / 2), 0, 0))


def build(carriage_x=0.0):
    st, ly = assembly.stack(), assembly.bracket_layout()
    ext_y_rear, ext_y_front = EXT_HOLES[1][0], EXT_HOLES[0][0]
    ext_z = EXT_HOLES[0][1]
    shapes = {}
    shapes["plate_right"] = side_plate_placed(+1)
    shapes["plate_left"] = side_plate_placed(-1)
    for name, y in (("ext_rear", ext_y_rear), ("ext_front", ext_y_front)):
        shapes[name] = cq.Workplane("XY").box(PLATE_INNER_SPACING, EXT_SIZE, EXT_SIZE).translate((0, y, ext_z)).val()
    # feed roller + shaft (axis along X, at Y=0, Z=-20); shaft passes through the plates' shaft holes
    roller_len = PLATE_INNER_SPACING - 2 * 5.0
    shapes["roller"] = cq.Workplane("YZ").circle(ROLLER_D / 2).circle(SHAFT_D / 2).extrude(roller_len).translate((-roller_len / 2, 0, -20.0)).val()   # bored for the shaft
    shaft_len = PLATE_INNER_SPACING + 2 * (SIDE_PLATE["t"] + 4.0)
    shapes["shaft"] = cq.Workplane("YZ").circle(SHAFT_D / 2).extrude(shaft_len).translate((-shaft_len / 2, 0, -20.0)).val()
    b = BEARING_608
    for sign in (-1, 1):
        xc = sign * (PLATE_INNER_SPACING / 2 + SIDE_PLATE["t"] - b["w"] / 2)
        ring = cq.Workplane("YZ").circle(b["od"] / 2).circle(b["id"] / 2).extrude(b["w"]).translate((xc - b["w"] / 2, 0, -20.0)).val()
        shapes["bearing_%s" % ("r" if sign > 0 else "l")] = ring
    # platen halves (top face = paper plane) and support posts
    platen_cy = (ly["platen_y"][0] + ly["platen_y"][1]) / 2
    platen_cz = st["paper_top"] - PLATEN_HALF["t"] / 2
    shapes["platen_left"] = _place(parts.PARTS["platen_half"](), -PLATEN_HALF["l"] / 2, platen_cy, platen_cz)
    shapes["platen_right"] = _place(parts.PARTS["platen_half_right"](), PLATEN_HALF["l"] / 2, platen_cy, platen_cz)
    ext_bottom = ext_z - EXT_SIZE / 2
    for k, x in enumerate(POST_X):
        wp = parts.platen_post(joint=(x == 0.0))
        shapes["post_%d" % k] = _place(wp, x, ext_y_rear, ext_bottom)
    # carriage bracket (local +y = front = machine -Y, so turn 180 about Z), holder under the shelf, placeholder cartridge in the holder
    plate_cz = st["block_top"] + PLATE_T / 2
    shapes["bracket"] = _place(parts.carriage_bracket(), carriage_x, ext_y_rear, plate_cz, rot_z=180)
    H = parts.holder_height()
    holder_cy = ly["front_plate"] - SHELF_LEN / 2
    shapes["holder"] = _place(parts.cartridge_holder(), carriage_x, holder_cy, st["shelf_bottom"] - H / 2)
    shapes["cartridge"] = cq.Workplane("XY").box(HP45_BOX["w"], HP45_BOX["l"], HP45_BOX["h"]).translate(
        (carriage_x, holder_cy, st["nozzle_z"] + HP45_BOX["h"] / 2)).val()
    return shapes


def interferences(shapes, tol=1e-3):
    """[(a, b, intersection volume mm^3)] for every pair whose bounding boxes overlap and whose boolean intersection has volume > tol."""
    out = []
    for (na, a), (nb, b) in itertools.combinations(shapes.items(), 2):
        ba, bb = a.BoundingBox(), b.BoundingBox()
        if (ba.xmax < bb.xmin or bb.xmax < ba.xmin or ba.ymax < bb.ymin or bb.ymax < ba.ymin or ba.zmax < bb.zmin or bb.zmax < ba.zmin):
            continue
        v = a.intersect(b).Volume()
        if v > tol:
            out.append((na, nb, round(v, 3)))
    return out


if __name__ == "__main__":
    for cx in (-139.0, -130.0, 0.0, 130.0, 139.0):
        print("carriage_x", cx, interferences(build(cx)) or "no interference")
