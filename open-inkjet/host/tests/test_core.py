import numpy as np
import pytest
from openinkjet.heads import HP45
from openinkjet import geometry as g
from openinkjet.slicer import slice_page, swath_feed_mm


def test_hp45_swath_is_12_7mm():
    assert HP45.swath_mm == pytest.approx(12.7)


def test_dot_pitch_300dpi():
    assert g.dot_pitch_mm(300) == pytest.approx(0.084667, abs=1e-6)


def test_swath_count_a4():
    # 600 vdpi: 300 rows/swath, A4 297mm -> ~7016 rows -> ceil(23.4) = 24 swaths
    assert g.swath_count(297.0, HP45, 600) == 24
    # 300 vdpi: 150 rows/swath = 12.7mm -> same 24
    assert g.swath_count(297.0, HP45, 300) == 24


def test_max_speed_300dpi():
    assert g.max_carriage_speed_mm_s(HP45, 300) == pytest.approx(18000 * 25.4 / 300)


def test_encoder_counts():
    assert g.encoder_counts_per_dot(150, True, 300) == pytest.approx(2.0)


def test_slice_roundtrip_600():
    rng = np.random.default_rng(0)
    img = (rng.random((700, 50)) > 0.5).astype(np.uint8)
    sw = slice_page(img, HP45, 600)
    assert len(sw) == 3 and all(s.shape == (50, 300) for s in sw)
    rebuilt = np.concatenate([s.T for s in sw], axis=0)[:700]
    assert np.array_equal(rebuilt, img)


def test_slice_300_uses_even_nozzles_only():
    img = np.ones((150, 4), dtype=np.uint8)
    (s,) = slice_page(img, HP45, 300)
    assert s[:, ::2].all() and not s[:, 1::2].any()
    assert swath_feed_mm(HP45, 300) == pytest.approx(12.7)


def test_bad_vdpi():
    with pytest.raises(ValueError):
        g.swath_count(297, HP45, 250)
