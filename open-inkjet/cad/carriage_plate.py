"""Carriage adapter plate: bolts to an MGN9H block; has a 2-hole pattern for the cartridge holder
(pattern is a placeholder until the HP45 cartridge is measured)."""
import cadquery as cq
from params import MGN9H, PLATE_T, PLATE_MARGIN, BED_MM, HOLDER_HOLE_X


def build(holder_holes=((-HOLDER_HOLE_X, 0.0), (HOLDER_HOLE_X, 0.0)), holder_d=3.4):
    # wide enough that the holder bolts keep >= 2.3 mm edge distance
    w = max(MGN9H["width"] + 2 * PLATE_MARGIN, 2 * (HOLDER_HOLE_X + holder_d / 2 + 2.3))
    l = MGN9H["length"] + 2 * PLATE_MARGIN
    plate = cq.Workplane("XY").box(w, l, PLATE_T)
    # clearance holes for M3 (3.4 mm) at the carriage bolt pattern
    bx, by = MGN9H["bolt_x"] / 2, MGN9H["bolt_y"] / 2
    plate = plate.faces(">Z").workplane().pushPoints(
        [(sx * bx, sy * by) for sx in (-1, 1) for sy in (-1, 1)]).hole(3.4)
    plate = plate.faces(">Z").workplane().pushPoints(list(holder_holes)).hole(holder_d)
    return plate


if __name__ == "__main__":
    p = build()
    bb = p.val().BoundingBox()
    assert max(bb.xlen, bb.ylen, bb.zlen) <= BED_MM
    cq.exporters.export(p, "carriage_plate.stl")
    print("bbox", round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2), "vol_mm3", round(p.val().Volume(), 1))
