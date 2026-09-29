# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
import math
import cadquery as cq
import pytest
from params import *
from parts import PARTS
import carriage_plate, assembly


def build(name):
    return carriage_plate.build() if name == "carriage_plate" else PARTS[name]()


def cyl_holes(wp, min_r=1.0):
    """[(cx, cy, r, zmin, zmax)] for every cylindrical face with its axis along Z (bbox-based, seam-safe)."""
    out = {}
    for f in wp.faces("%CYLINDER").vals():
        bb = f.BoundingBox()
        r = (bb.xlen + bb.ylen) / 4
        if r < min_r or abs(bb.xlen - bb.ylen) > 0.2:      # skip partial/non-round faces
            continue
        key = (round((bb.xmin + bb.xmax) / 2, 2), round((bb.ymin + bb.ymax) / 2, 2), round(r, 2))
        z0, z1 = out.get(key, (1e9, -1e9))
        out[key] = (min(z0, bb.zmin), max(z1, bb.zmax))
    return [(k[0], k[1], k[2], v[0], v[1]) for k, v in out.items()]


@pytest.mark.parametrize("name", list(PARTS) + ["carriage_plate"])
def test_part_is_valid_and_fits_bed(name):
    wp = build(name); s = wp.val()
    assert s.isValid() and s.Volume() > 0
    bb = s.BoundingBox()
    assert max(bb.xlen, bb.ylen) <= BED_MM and bb.zlen <= 250
    assert len(wp.solids().vals()) == 1                       # one connected solid


@pytest.mark.parametrize("name", list(PARTS) + ["carriage_plate"])
def test_holes_keep_wall_and_edge_distance(name):
    wp = build(name); bb = wp.val().BoundingBox()
    holes = cyl_holes(wp)
    for (x, y, r, _, _) in holes:
        # >= 2 mm of material between hole wall and the part's outer bounding faces (x/y)
        assert x - r - bb.xmin >= 2.0 and bb.xmax - x - r >= 2.0, (name, x, y, r)
        assert y - r - bb.ymin >= 2.0 and bb.ymax - y - r >= 2.0, (name, x, y, r)
    for i, a in enumerate(holes):                             # >= 1.2 mm wall between neighbouring holes
        for b in holes[i + 1:]:
            if abs((a[0], a[1]) == (b[0], b[1])) or (a[0], a[1]) == (b[0], b[1]):
                continue                                       # concentric (seat + shaft hole) is intended
            assert math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2] >= 1.2, (name, a, b)


def test_side_plate_hole_positions():
    holes = cyl_holes(PARTS["side_plate"]())
    have = {(h[0], h[1], h[2]) for h in holes}
    for (x, y) in EXT_HOLES:
        assert (x, y, EXT_HOLE_D / 2) in have
    assert (0.0, -20.0, (BEARING_608["od"] + BEARING_SEAT_CLEAR) / 2) in have      # bearing seat
    assert (0.0, -20.0, SHAFT_HOLE_D / 2) in have                                  # shaft through-hole


def test_side_plate_seat_depth_floor_and_shaft_exit():
    sp = SIDE_PLATE; t = sp["t"]
    seat = [h for h in cyl_holes(PARTS["side_plate"]()) if abs(h[2] - (BEARING_608["od"] + BEARING_SEAT_CLEAR) / 2) < 0.01][0]
    depth = seat[4] - seat[3]
    assert depth == pytest.approx(BEARING_608["w"], abs=0.01)                      # 608 is 7 mm wide
    assert t - depth >= 2.0                                                        # floor >= 2 mm (several layers)
    shaft = [h for h in cyl_holes(PARTS["side_plate"]()) if abs(h[2] - SHAFT_HOLE_D / 2) < 0.01][0]
    assert shaft[4] - shaft[3] == pytest.approx(t - depth, abs=0.01)        # cuts the whole 3 mm floor -> shaft exits
    assert shaft[3] == pytest.approx(-t / 2, abs=0.01) and SHAFT_HOLE_D > SHAFT_D   # open on the outer face, with clearance


def test_holder_bolts_match_carriage_plate_and_hit_flange():
    plate = {(h[0], h[1]) for h in cyl_holes(carriage_plate.build())}
    hold = {(h[0], h[1]) for h in cyl_holes(PARTS["cartridge_holder"]())}
    for sx in (-1, 1):
        assert (sx * HOLDER_HOLE_X, 0.0) in plate and (sx * HOLDER_HOLE_X, 0.0) in hold


def test_holder_pocket_is_enclosed_with_walls():
    s = PARTS["cartridge_holder"]().val()
    c = cq.Workplane("XY").box(1, 1, 1).translate((0, 0, 3.0))            # a point inside the pocket, above the floor
    assert not s.isInside(cq.Vector(0, 0, 5.0))                            # pocket is empty
    assert s.isInside(cq.Vector(HP45_BOX["w"] / 2 + 1.5, 0, 0))            # 3 mm wall present on the sides
    assert s.isInside(cq.Vector(0, 0, -HP45_BOX["h"] * 0.25 + 1.0))        # floor present


def test_roller_block_wall_and_shaft():
    holes = cyl_holes(PARTS["roller_block"]())
    r_seat = (BEARING_608["od"] + BEARING_SEAT_CLEAR) / 2
    assert any(abs(h[2] - SHAFT_HOLE_D / 2) < 0.01 for h in holes)
    for h in holes:
        if abs(h[2] - 1.7) < 0.01:
            assert math.hypot(h[0], h[1]) - 1.7 - r_seat >= 1.2            # bolt hole to bearing bore wall


def test_carriage_plate_volume_hand_calc():
    bb = carriage_plate.build().val().BoundingBox()
    w, l = bb.xlen, bb.ylen
    assert w == pytest.approx(max(MGN9H["width"] + 2 * PLATE_MARGIN, 2 * (HOLDER_HOLE_X + 1.7 + 2.3)))
    holes = 6 * math.pi * 1.7 ** 2 * PLATE_T
    assert carriage_plate.build().val().Volume() == pytest.approx(w * l * PLATE_T - holes, rel=1e-3)


def test_assembly_budget():
    c = assembly.checks()
    assert c["stroke_slack_mm"] >= 20 and c["rail_fits_between_plates"]
    assert c["rail_holes"] == len(assembly.rail_holes()) == 17
    tail = RAIL_LEN - assembly.rail_holes()[-1]
    assert RAIL_EDGE <= tail < RAIL_EDGE + RAIL_HOLE_PITCH                      # tail edge within one pitch of head edge
    assert 40 < c["feed_steps_per_mm"] < 60
    assert 2 * PAGE_MARGIN + PAGE_W + PARK_ZONE == c["required_stroke_mm"]


def test_motor_mount_matches_nema17_flange():
    holes = cyl_holes(PARTS["motor_mount"]())
    have = {(h[0], h[1], h[2]) for h in holes}
    for sx in (-1, 1):
        for sy in (-1, 1):
            assert (sx * NEMA17["hole_pitch"] / 2, sy * NEMA17["hole_pitch"] / 2, NEMA17["hole_d"] / 2) in have
    assert (0.0, 0.0, (NEMA17["pilot"] + 0.5) / 2) in have                         # pilot clearance bore
    bb = PARTS["motor_mount"]().val().BoundingBox()
    assert bb.xlen >= NEMA17["face"]                                                # plate covers the 42.3 mm flange


def test_carriage_bracket_reaches_paper_with_correct_gap():
    st = assembly.stack()
    wp = PARTS["carriage_bracket"]()
    bb = wp.val().BoundingBox()
    assert bb.zlen == pytest.approx(st["riser_h"], abs=0.01)                        # plate top to shelf bottom
    # cartridge hangs from the shelf underside: nozzle face = shelf bottom - cartridge height must sit NOZZLE_GAP above the paper
    assert st["shelf_bottom"] - HP45_BOX["h"] - st["paper_top"] == pytest.approx(NOZZLE_GAP)
    holes = cyl_holes(wp)
    shelf_holes = [h for h in holes if abs(abs(h[0]) - HOLDER_HOLE_X) < 0.01 and h[2] == pytest.approx(1.7)]
    assert len(shelf_holes) == 2                                                    # same +-17 mm pattern as the holder flanges
    hold = {(h[0], h[1]) for h in cyl_holes(PARTS["cartridge_holder"]())}
    assert {(h[0], 0.0) for h in shelf_holes} == hold                               # x positions match; y is the shelf centre


def test_holder_flanges_are_at_the_top_to_meet_the_shelf():
    s = PARTS["cartridge_holder"]().val()
    hh = HP45_BOX["h"] * 0.5
    assert s.isInside(cq.Vector(HOLDER_HOLE_X + 5.5, 4.0, hh / 2 - 1.5))            # flange material at the top
    assert not s.isInside(cq.Vector(HOLDER_HOLE_X + 5.5, 4.0, -hh / 2 + 1.5))       # none at the bottom


def test_platen_halves_cover_a4_and_fit_bed():
    assert 2 * PLATEN_HALF["l"] >= PAGE_W + 2 * PAGE_MARGIN and PLATEN_HALF["l"] <= BED_MM


def test_stack_checks():
    c = assembly.checks()
    assert c["riser_positive"] and c["shelf_clears_extrusion_y"]
    assert c["nozzle_gap_mm"] == pytest.approx(NOZZLE_GAP)
    assert c["stack_paper_top"] == -10.0 and c["stack_block_top"] == pytest.approx(70.0)
