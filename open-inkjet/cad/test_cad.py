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


def test_holder_has_walls_floor_rim_and_nozzle_window():
    s = PARTS["cartridge_holder"]().val()
    H = HP45_BOX["h"] + HOLDER_RIM_T
    assert not s.isInside(cq.Vector(0, 0, 0))                                          # pocket is empty
    assert s.isInside(cq.Vector(HP45_BOX["w"] / 2 + HOLDER_WALL / 2, 0, 0))            # side wall present
    assert s.isInside(cq.Vector(HP45_BOX["w"] / 2 - HOLDER_RIM_W / 2, 0, -H / 2 + HOLDER_RIM_T / 2))   # rim the cartridge rests on
    assert not s.isInside(cq.Vector(0, 0, -H / 2 + HOLDER_RIM_T / 2))                  # nozzle window through the floor
    assert not s.isInside(cq.Vector(0, 0, H / 2 - 0.1))                                # open at the top (cartridge goes in from above)


def test_cartridge_fits_holder_and_stack_numbers_close():
    st = assembly.stack()
    H = HP45_BOX["h"] + HOLDER_RIM_T
    holder = PARTS["cartridge_holder"]().val()
    cart = cq.Workplane("XY").box(HP45_BOX["w"], HP45_BOX["l"], HP45_BOX["h"]).translate((0, 0, HOLDER_RIM_T / 2)).val()
    assert holder.intersect(cart).Volume() == pytest.approx(0.0, abs=1e-6)             # cartridge sits inside the sleeve, touching only
    cb = cart.BoundingBox()
    assert cb.zmin == pytest.approx(-H / 2 + HOLDER_RIM_T) and cb.zmax == pytest.approx(H / 2)    # on the rim, top flush with the holder top
    assert st["shelf_bottom"] - H + HOLDER_RIM_T == pytest.approx(st["nozzle_z"])      # nozzle face where the stack says
    assert st["nozzle_z"] - st["paper_top"] == pytest.approx(NOZZLE_GAP)               # and NOZZLE_GAP above the paper


def test_holder_flanges_are_at_the_top_to_meet_the_shelf():
    s = PARTS["cartridge_holder"]().val()
    H = HP45_BOX["h"] + HOLDER_RIM_T
    assert s.isInside(cq.Vector(HOLDER_HOLE_X + 5.5, 4.0, H / 2 - 1.5))                # flange material at the top
    assert not s.isInside(cq.Vector(HOLDER_HOLE_X + 5.5, 4.0, -H / 2 + 1.5))           # none at the bottom


def test_carriage_plate_volume_hand_calc():
    bb = carriage_plate.build().val().BoundingBox()
    w, l = bb.xlen, bb.ylen
    assert w == pytest.approx(max(MGN9H["length"] + 2 * PLATE_MARGIN, 2 * (HOLDER_HOLE_X + 1.7 + 2.3)))   # x along the rail
    assert l == pytest.approx(MGN9H["width"] + 2 * PLATE_MARGIN)                                            # y across the rail
    holes = 6 * math.pi * 1.7 ** 2 * PLATE_T
    assert carriage_plate.build().val().Volume() == pytest.approx(w * l * PLATE_T - holes, rel=1e-3)
    pts = {(h[0], h[1]) for h in cyl_holes(carriage_plate.build()) if h[2] == pytest.approx(1.7)}
    for sx in (-1, 1):
        for sy in (-1, 1):
            assert (sx * MGN9H["bolt_along"] / 2, sy * MGN9H["bolt_across"] / 2) in pts       # along-rail pitch on x, across-rail on y


def test_roller_block_wall_and_shaft():
    holes = cyl_holes(PARTS["roller_block"]())
    r_seat = (BEARING_608["od"] + BEARING_SEAT_CLEAR) / 2
    assert any(abs(h[2] - SHAFT_HOLE_D / 2) < 0.01 for h in holes)
    for h in holes:
        if abs(h[2] - 1.7) < 0.01:
            assert math.hypot(h[0], h[1]) - 1.7 - r_seat >= 1.2            # bolt hole to bearing bore wall


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
    assert (0.0, 0.0, (NEMA17["pilot"] + PILOT_CLEAR) / 2) in have                  # pilot clearance bore (23 mm for a 22 mm boss)
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


def test_platen_halves_span_the_frame_and_fit_bed():
    assert 2 * PLATEN_HALF["l"] >= PLATE_INNER_SPACING and PLATEN_HALF["l"] <= BED_MM and 2 * PLATEN_HALF["l"] >= PAGE_W + 2 * PAGE_MARGIN


def test_stack_checks():
    c = assembly.checks()
    assert c["riser_positive"] and c["riser_clears_extrusion_mm"] >= 3.0                # 6 mm between the riser and the extrusion face
    assert c["holder_clearance_to_paper_mm"] >= 1.0                                    # holder bottom stays 1 mm clear of the paper plane (cockle)
    assert c["holder_inside_shelf"] and c["cartridge_supported"]                       # holder footprint on the shelf; cartridge over roller+platen, clear of the lip
    assert c["nozzle_gap_mm"] == pytest.approx(NOZZLE_GAP)
    assert c["stack_paper_top"] == -10.0 and c["stack_block_top"] == pytest.approx(70.0)


def _machine_x_holes(part_name, centre_x):
    return sorted(round(h[0] + centre_x, 3) for h in cyl_holes(PARTS[part_name]()) if h[2] == pytest.approx(1.7))


def test_platen_holes_land_on_the_post_feet():
    left = _machine_x_holes("platen_half", -PLATEN_HALF["l"] / 2)
    right = _machine_x_holes("platen_half_right", +PLATEN_HALF["l"] / 2)
    assert left == [-130.0, -5.0] and right == [5.0, 130.0]                   # outer posts at +-130, joint post (feet holes at +-5) at 0
    joint = sorted(round(h[0] + POST_X[1], 3) for h in cyl_holes(PARTS["platen_post_joint"]()) if h[2] == pytest.approx(1.7))
    assert joint == [-5.0, 5.0]
    outer = [round(h[0], 3) for h in cyl_holes(PARTS["platen_post_outer"]()) if h[2] == pytest.approx(1.7)]
    assert outer == [0.0]                                                      # centred on the post (posts at -130 and 130)


def test_post_geometry_matches_the_stack():
    pl = assembly.post_layout()
    bb = PARTS["platen_post_outer"]().val().BoundingBox()
    assert bb.zmax == pytest.approx(0.0) and bb.zmin == pytest.approx(pl["foot_bottom"] - pl["ext_bottom"])    # flange top at the extrusion bottom, foot under the platen
    c = assembly.checks()
    assert c["post_clears_carriage_mm"] >= 3.0 and c["post_foot_clear_of_roller_mm"] >= 1.0 and c["platen_spans_plates"]
    m5 = [h for h in cyl_holes(PARTS["platen_post_outer"]()) if h[2] == pytest.approx(M5_HOLE_D / 2)]
    assert len(m5) == 1 and (m5[0][0], m5[0][1]) == (0.0, 0.0)                 # M5 over the T-slot centre


def test_motor_mount_bolts_match_the_side_plate_pattern():
    mount = {(h[0], h[1]) for h in cyl_holes(PARTS["motor_mount"]()) if h[2] == pytest.approx(1.7)}
    plate = {(h[0], h[1] + 20.0) for h in cyl_holes(PARTS["side_plate"]()) if h[2] == pytest.approx(1.7) and abs(h[1] + 20.0) > 5}
    corners = {(sx * MOTOR_BOLT_SQUARE, sy * MOTOR_BOLT_SQUARE) for sx in (-1, 1) for sy in (-1, 1)}
    assert corners <= mount and corners <= plate                               # same square on both parts, relative to the roller axis


def test_sensor_and_encoder_brackets_have_a_slot_bolt():
    for name in ("sensor_mount", "encoder_bracket"):
        m5 = [h for h in cyl_holes(PARTS[name]()) if h[2] == pytest.approx(M5_HOLE_D / 2)]
        assert len(m5) == 1, name


# ---- full 3D assembly: pairwise boolean interference ----
import assembly_model as am


@pytest.mark.parametrize("cx", [-139.0, -130.0, 0.0, 130.0, 139.0])
def test_assembly_has_no_interference_at_carriage_positions(cx):
    shapes = am.build(cx)
    assert len(shapes) == 17 and all(s.isValid() for s in shapes.values())
    assert am.interferences(shapes) == []


def test_assembly_check_detects_real_interference():
    shapes = am.build(0.0)
    c = shapes["cartridge"].translate(cq.Vector(0, 0, 10.0))                   # cartridge pushed 10 mm up into the holder/shelf
    shapes["cartridge"] = c
    assert any("cartridge" in (a, b) for a, b, v in am.interferences(shapes))
    shapes = am.build(0.0)
    shapes["bracket"] = shapes["bracket"].translate(cq.Vector(0, 0, -12.0))    # bracket dropped onto the extrusion
    assert any("bracket" in (a, b) and "ext_rear" in (a, b) for a, b, v in am.interferences(shapes))
    shapes = am.build(0.0)
    shapes["post_1"] = shapes["post_1"].translate(cq.Vector(0, -12.0, 0))      # a post stem moved into the carriage riser region
    assert any("post_1" in (a, b) for a, b, v in am.interferences(shapes))


def test_assembly_contacts_are_real_touches_not_gaps():
    """Parts that must touch do (their boxes meet): plate/extrusion ends, post flange/extrusion bottom, post foot/platen underside."""
    s = am.build(0.0)
    assert s["ext_rear"].BoundingBox().xmax == pytest.approx(s["plate_right"].BoundingBox().xmin)
    assert s["post_1"].BoundingBox().zmax == pytest.approx(s["ext_rear"].BoundingBox().zmin)
    assert s["platen_left"].BoundingBox().zmin == pytest.approx(-16.0)
    assert s["post_0"].BoundingBox().zmin == pytest.approx(s["platen_left"].BoundingBox().zmin - POST_FOOT_T)
    nozzle_gap = s["cartridge"].BoundingBox().zmin - (-10.0)
    assert nozzle_gap == pytest.approx(NOZZLE_GAP)                             # cartridge underside NOZZLE_GAP above the paper plane


@pytest.mark.parametrize("cx", [-145.0, -139.0, -130.0, 0.0, 130.0, 139.0, 145.0])
def test_assembly_minimum_clearances(cx):
    """Interference passes touching parts, so also assert real gaps between things that must NOT touch (found by review: the riser was 2 mm, not 6)."""
    s = am.build(cx)
    d = am.min_distance
    assert d(s["bracket"], s["ext_rear"]) >= 3.0                                    # riser and plate keep off the extrusion (top plate rides above it)
    for k in range(3):
        assert d(s["bracket"], s["post_%d" % k]) >= 3.0                             # carriage can pass every post
        assert d(s["holder"], s["post_%d" % k]) >= 3.0
    assert d(s["holder"], s["platen_left"]) >= 1.0 and d(s["holder"], s["platen_right"]) >= 1.0
    assert d(s["holder"], s["roller"]) >= 1.0
    assert d(s["cartridge"], s["platen_left"]) >= NOZZLE_GAP - 1e-6 or d(s["cartridge"], s["platen_right"]) >= NOZZLE_GAP - 1e-6
    for plate in ("plate_left", "plate_right"):
        assert d(s["bracket"], s[plate]) >= 3.0
    # OPEN DESIGN ITEM (found by review): the 23 mm pilot bore leaves a radial gap of (23 - 22) / 2 around the 22 mm bearing, so the mount does NOT retain it.
    assert d(s["motor_mount"], s["bearing_r"]) == pytest.approx((NEMA17["pilot"] + PILOT_CLEAR - BEARING_608["od"]) / 2, abs=1e-6)


def test_riser_clearance_is_what_the_layout_claims():
    c = assembly.checks()
    s = am.build(0.0)
    measured = am.min_distance(s["bracket"], s["ext_rear"])
    assert measured >= c["riser_clears_extrusion_mm"] - 1e-6 and c["riser_clears_extrusion_mm"] >= 3.0
