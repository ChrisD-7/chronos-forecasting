"""Assembly-level consistency checks that need no CAD kernel: numbers that must agree across parts."""
from params import *


def required_travel():
    return PAGE_W + 2 * PAGE_MARGIN + CARRIAGE_BODY_W + PARK_ZONE


def checks():
    out = {}
    out["rail_long_enough"] = RAIL_LEN >= required_travel()
    out["rail_margin_mm"] = RAIL_LEN - required_travel()
    # page must fit between the inner faces of the side plates, leaving room for the frame span
    out["side_plate_spacing_mm"] = PAGE_W + 2 * PAGE_MARGIN + 2 * 25.0   # 25 mm each side for roller ends/bearings
    out["rail_spans_side_plates"] = RAIL_LEN <= out["side_plate_spacing_mm"] + 2 * SIDE_PLATE["t"] + 2 * 40.0
    return out


if __name__ == "__main__":
    for k, v in checks().items():
        print(k, v)
