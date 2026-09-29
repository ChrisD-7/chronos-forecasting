"""Slice a 1-bit page bitmap into per-swath column data for a nozzle-array head.

Output for each swath is an array (columns, nozzles) of uint8 {0,1}: for carriage column x, nozzle n
fires iff bit==1. Row->nozzle mapping at vdpi < nozzle_dpi uses every ratio-th nozzle."""
import numpy as np
from .heads import HeadSpec
from .geometry import nozzle_ratio


def slice_page(bitmap: np.ndarray, head: HeadSpec, vdpi: int):
    """bitmap: (rows, cols) array, 1 = ink. Returns list of (columns, nozzles) uint8 arrays."""
    if bitmap.ndim != 2:
        raise ValueError("bitmap must be 2-D")
    ratio = nozzle_ratio(head, vdpi)
    rows_per_swath = head.nozzles // ratio
    rows, cols = bitmap.shape
    n_sw = -(-rows // rows_per_swath)
    padded = np.zeros((n_sw * rows_per_swath, cols), dtype=np.uint8)
    padded[:rows] = (bitmap != 0)
    swaths = []
    for s in range(n_sw):
        block = padded[s * rows_per_swath:(s + 1) * rows_per_swath]   # (rows_per_swath, cols)
        out = np.zeros((cols, head.nozzles), dtype=np.uint8)
        out[:, ::ratio] = block.T
        swaths.append(out)
    return swaths


def swath_feed_mm(head: HeadSpec, vdpi: int) -> float:
    ratio = nozzle_ratio(head, vdpi)
    return (head.nozzles // ratio) * 25.4 / vdpi
