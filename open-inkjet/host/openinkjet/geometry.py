# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Page/carriage/encoder arithmetic for an A4, single-rail, sheet-fed printer."""
import math
from .heads import HeadSpec, MM_PER_INCH

A4_MM = (210.0, 297.0)  # width (carriage axis), length (feed axis)


def dot_pitch_mm(dpi: float) -> float:
    return MM_PER_INCH / dpi


def nozzle_ratio(head: HeadSpec, vdpi: int) -> int:
    """Every ratio-th nozzle prints at vdpi. Validates vdpi so slicer, feed and count agree."""
    if vdpi <= 0 or head.nozzle_dpi % vdpi:
        raise ValueError("vdpi must be a positive divisor of nozzle_dpi")
    ratio = head.nozzle_dpi // vdpi
    if head.nozzles % ratio:
        raise ValueError("nozzle count must be divisible by nozzle_dpi/vdpi")
    return ratio


def swath_count(page_len_mm: float, head: HeadSpec, vdpi: int) -> int:
    """Passes needed to cover page_len_mm. At vdpi < nozzle_dpi only every
    (nozzle_dpi/vdpi)-th nozzle is used, so the swath covers nozzles/(ratio) rows."""
    rows_per_swath = head.nozzles // nozzle_ratio(head, vdpi)
    rows = math.ceil(page_len_mm / dot_pitch_mm(vdpi))
    return math.ceil(rows / rows_per_swath)


def max_carriage_speed_mm_s(head: HeadSpec, hdpi: int) -> float:
    """Speed at which the head's max fire rate equals one dot per dot pitch."""
    return head.max_fire_hz * dot_pitch_mm(hdpi)


def encoder_counts_per_dot(encoder_lpi: int, quadrature: bool, hdpi: int) -> float:
    counts_per_inch = encoder_lpi * (4 if quadrature else 1)
    return counts_per_inch / hdpi


def travel_mm(page_w_mm: float, margin_mm: float, carriage_w_mm: float,
              park_mm: float) -> float:
    """Rail travel: page + margin overshoot + carriage body offset + capping/park zone."""
    return page_w_mm + 2 * margin_mm + carriage_w_mm + park_mm
