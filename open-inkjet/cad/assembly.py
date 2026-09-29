# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Assembly-level consistency checks that need no CAD kernel: numbers that must agree across parts."""
import math
from params import *


def required_stroke():
    """Carriage travel needed: page + margins + park zone (capping/wiping)."""
    return PAGE_W + 2 * PAGE_MARGIN + PARK_ZONE


def available_stroke():
    """Carriage-block travel on the rail after subtracting the block and end-stop room."""
    return RAIL_LEN - CARRIAGE_BODY_W - 2 * STOP_MARGIN


def rail_holes():
    n = int((RAIL_LEN - 2 * RAIL_EDGE) // RAIL_HOLE_PITCH) + 1
    return [RAIL_EDGE + i * RAIL_HOLE_PITCH for i in range(n)]


def feed_steps_per_mm():
    return MOTOR_FULL_STEPS * MICROSTEPS / (math.pi * ROLLER_D)     # roller drive, no gearing


def checks():
    out = {}
    out["required_stroke_mm"] = required_stroke()
    out["available_stroke_mm"] = available_stroke()
    out["stroke_slack_mm"] = available_stroke() - required_stroke()
    out["rail_holes"] = len(rail_holes())
    out["backing_extrusion_len_mm"] = RAIL_LEN                       # rail is bolted along its full length
    out["side_plate_inner_spacing_mm"] = PLATE_INNER_SPACING
    out["rail_fits_between_plates"] = RAIL_LEN <= PLATE_INNER_SPACING
    out["feed_steps_per_mm"] = feed_steps_per_mm()
    return out


if __name__ == "__main__":
    for k, v in checks().items():
        print(k, v)
