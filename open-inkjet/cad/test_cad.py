import math
import cadquery as cq
import pytest
from params import BED_MM, SIDE_PLATE, BEARING_608
from parts import PARTS
import carriage_plate, assembly


@pytest.mark.parametrize("name", list(PARTS) + ["carriage_plate"])
def test_part_is_valid_and_fits_bed(name):
    wp = carriage_plate.build() if name == "carriage_plate" else PARTS[name]()
    s = wp.val()
    assert s.isValid() and s.Volume() > 0
    bb = s.BoundingBox()
    assert max(bb.xlen, bb.ylen) <= BED_MM and bb.zlen <= 250
    assert len(wp.solids().vals()) == 1            # one connected solid, nothing floating


def test_side_plate_volume_matches_hand_calc():
    sp = SIDE_PLATE
    holes = 2 * math.pi * (3.5 / 2) ** 2 * sp["t"] + 2 * math.pi * (5.5 / 2) ** 2 * sp["t"]
    seat = math.pi * (BEARING_608["od"] / 2) ** 2 * BEARING_608["w"]
    assert PARTS["side_plate"]().val().Volume() == pytest.approx(sp["w"] * sp["h"] * sp["t"] - holes - seat, rel=1e-3)


def test_assembly_rail_and_spacing():
    c = assembly.checks()
    assert c["rail_long_enough"] and c["rail_margin_mm"] >= 0
    assert c["rail_spans_side_plates"]
