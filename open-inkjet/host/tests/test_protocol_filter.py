import struct, numpy as np, pytest
from PIL import Image
from openinkjet import protocol as p
from openinkjet.filter import frames_for_image, pack_columns
from openinkjet.halftone import floyd_steinberg


def test_crc_known_vector():
    assert p.crc16(b"123456789") == 0x29B1   # CRC-16/CCITT-FALSE check value


def test_roundtrip_and_corruption():
    f = p.encode(p.T_ACK, b"xyz")
    t, pl, n = p.decode(f)
    assert (t, pl, n) == (p.T_ACK, b"xyz", len(f))
    bad = bytearray(f); bad[5] ^= 1
    with pytest.raises(ValueError):
        p.decode(bytes(bad))


def test_pack_columns_bit_order():
    sw = np.zeros((2, 300), dtype=np.uint8); sw[0, 0] = 1; sw[1, 9] = 1
    b = pack_columns(sw)
    assert len(b) == 2 * 38 and b[0] == 1 and b[38 + 1] == 2


def test_halftone_extremes_and_mean():
    assert floyd_steinberg(np.full((8, 8), 255)).sum() == 0
    assert floyd_steinberg(np.zeros((8, 8))).sum() == 64
    m = floyd_steinberg(np.full((64, 64), 128)).mean()
    assert 0.45 < m < 0.55


def test_full_page_stream_parses_and_reassembles():
    img = Image.new("L", (210, 297), 0)  # all black, A4 aspect
    buf = b"".join(frames_for_image(img))
    hdrs, data = [], {}
    while buf:
        t, pl, n = p.decode(buf); buf = buf[n:]
        if t == p.T_SWATH_HDR:
            hdrs.append(struct.unpack("<HIHbI", pl)); data[hdrs[-1][0]] = bytearray()
        elif t == p.T_SWATH_DATA:
            off = struct.unpack_from("<I", pl)[0]
            assert off == len(data[hdrs[-1][0]]); data[hdrs[-1][0]] += pl[4:]
    assert len(hdrs) == 24
    idx, columns, bpc, d, feed = hdrs[1]
    assert (columns, bpc, feed) == (2480, 38, 12700) and len(data[1]) == columns * bpc
    assert [h[3] for h in hdrs[:3]] == [1, -1, 1]
    # margin: first and last swath columns are partly/fully white, an interior swath's centre column is inked
    mid = np.unpackbits(np.frombuffer(bytes(data[5][1240 * 38:1241 * 38]), dtype=np.uint8), bitorder="little")[:300]
    assert mid[::2].all() and not mid[1::2].any()
    edge_col0 = np.frombuffer(bytes(data[5][:38]), dtype=np.uint8)
    assert not edge_col0.any()   # left margin column stays white


def test_column_order_is_not_reversed_for_leftward_swaths():
    # asymmetric image: only the left half is black -> every swath's first columns inked, last columns blank
    img = Image.new("L", (210, 297), 255); img.paste(0, (0, 0, 105, 297))
    frames = list(frames_for_image(img)); 
    seen = {}
    cur = None
    for f in frames:
        t, pl, _ = p.decode(f)
        if t == p.T_SWATH_HDR: cur = struct.unpack("<HIHbI", pl)[0]; seen[cur] = bytearray()
        elif t == p.T_SWATH_DATA: seen[cur] += pl[4:]
    for idx in (5, 6):   # 5 = rightward, 6 = leftward; both must carry the same left-to-right data
        b = np.frombuffer(bytes(seen[idx]), dtype=np.uint8).reshape(2480, 38)
        assert b[400].any() and not b[2000].any()


def test_alpha_transparent_prints_white():
    img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))   # black rgb under alpha 0
    from openinkjet.filter import page_bitmap
    assert page_bitmap(img, 300, 300).sum() == 0


def test_aspect_ratio_preserved_and_centred():
    from openinkjet.filter import page_bitmap
    bm = page_bitmap(Image.new("L", (100, 100), 0), 300, 300)  # square -> 2480 wide limited
    ys, xs = np.nonzero(bm)
    assert abs((xs.max() - xs.min()) - (ys.max() - ys.min())) <= 2
    assert abs((xs.min() + xs.max()) / 2 - 2480 / 2) <= 2 and abs((ys.min() + ys.max()) / 2 - 3508 / 2) <= 2


def test_decode_distinguishes_truncated_from_corrupt():
    f = p.encode(p.T_ACK, b"abcd")
    with pytest.raises(p.NeedMore):
        p.decode(f[:-3])
    with pytest.raises(ValueError) as e:
        p.decode(b"\x00" + f[1:])
    assert not isinstance(e.value, p.NeedMore)


def test_sender_retransmits_on_nak_and_timeout_and_gives_up():
    from openinkjet.sender import send_frames, LinkError
    frames = [p.encode(p.T_START_PASS), p.encode(p.T_START_PASS)]
    replies = iter([p.T_NAK, None, p.T_ACK, p.T_ACK])
    sent = []
    send_frames(frames, sent.append, lambda: next(replies))
    assert len(sent) == 4
    with pytest.raises(LinkError):
        send_frames(frames[:1], lambda b: None, lambda: p.T_NAK, retries=2)


def test_max_payload_matches_firmware_header():
    import re, pathlib
    hdr = (pathlib.Path(__file__).parents[2] / "firmware/core/oi_proto.h").read_text()
    assert int(re.search(r"OI_MAX_PAYLOAD (\d+)", hdr).group(1)) == p.MAX_PAYLOAD
    assert int(re.search(r"OI_SOF (0x[0-9A-Fa-f]+)", hdr).group(1), 16) == p.SOF
