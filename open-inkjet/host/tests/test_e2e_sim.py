# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""End-to-end: host filter -> frames -> REAL C firmware core in a simulated printer -> printed page == input bitmap."""
import os, select, struct, subprocess, tempfile
import numpy as np
import pytest
from PIL import Image
from openinkjet import protocol as p
from openinkjet.filter import frames_for_image, page_bitmap
from openinkjet.sender import send_frames, LinkError

FW = os.path.join(os.path.dirname(__file__), "..", "..", "firmware")
SIM = None   # set by the build_sim fixture (private temp dir)


@pytest.fixture(scope="session", autouse=True)
def build_sim(tmp_path_factory):
    global SIM
    SIM = str(tmp_path_factory.mktemp("sim") / "oi_sim")
    src = ["tests/sim.c"] + [f"core/{n}.c" for n in ("oi_app", "oi_job", "oi_proto", "oi_sched", "oi_head_matrix", "oi_motion", "oi_maint")]
    subprocess.run(["gcc", "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-o", SIM] + src, cwd=FW, check=True)


def make_image():
    a = np.zeros((297, 210), np.uint8)
    yy, xx = np.mgrid[0:297, 0:210]
    a[:] = (255 * (xx / 210.0)).astype(np.uint8)                 # horizontal gradient
    a[100:110, :] = 0                                             # solid bar
    a[:, 100:103] = 0                                             # vertical line (checks column registration)
    a[200:210, 50:60] = 255
    return Image.fromarray(a, "L")


def read_pbm(path):
    with open(path, "rb") as f:
        assert f.readline().strip() == b"P4"
        w, h = map(int, f.readline().split())
        raw = np.frombuffer(f.read(), np.uint8).reshape(h, (w + 7) // 8)
    bm = np.unpackbits(raw, axis=1)[:, :w]
    full = np.zeros((24 * 150, 2480), np.uint8)          # sim writes only the inked bounding box; pad to page
    full[:h, :w] = bm
    return full


class Sim:
    def __init__(self, out, lag=0, bidir=0):
        self.proc = subprocess.Popen([SIM, out, str(lag), str(bidir)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.buf = b""

    def write(self, b):
        self.proc.stdin.write(b)

    def read_frame(self, timeout=0.3):
        fd = self.proc.stdout.fileno()
        while True:
            try:
                t, pl, n = p.decode(self.buf)
                self.buf = self.buf[n:]
                return t, pl
            except p.NeedMore:
                pass
            except ValueError:
                self.buf = self.buf[1:]
                continue
            r, _, _ = select.select([fd], [], [], timeout)
            if not r:
                return None
            self.buf += os.read(fd, 4096)

    def finish(self):
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode()
        rc = self.proc.wait(timeout=30)
        return rc, err


def print_page(img, lag=0, bidir=0, mangle=None):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "o.pbm")
        s = Sim(out, lag, bidir)
        write = s.write if mangle is None else mangle(s.write)
        send_frames(frames_for_image(img), write, s.read_frame)
        rc, err = s.finish()
        return read_pbm(out), rc, err


def expected(img):
    bm = page_bitmap(img, 300, 300)
    full = np.zeros((24 * 150, bm.shape[1]), np.uint8)
    full[:bm.shape[0]] = bm
    return full


def test_clean_link_prints_exact_page():
    img = make_image()
    got, rc, err = print_page(img)
    assert rc == 0, err
    assert "passes=24" in err and "naks=0" in err
    want = expected(img)
    assert got.shape == want.shape
    assert np.array_equal(got, want), f"{(got != want).sum()} differing dots"


def stat(err, key):
    return int(err.split(key + "=")[1].split()[0])


def test_maintenance_sequence_and_cap_safety():
    """The real application core must uncap once, spit before printing, wipe after the page, never fire into the
    closed cap, stay within the head fire-rate limit, and re-cap the head after the idle timeout."""
    got, rc, err = print_page(make_image())
    assert rc == 0, err
    assert stat(err, "uncap") == 1 and stat(err, "spit") == 1 and stat(err, "wipe") == 1
    assert stat(err, "capped_fire") == 0 and stat(err, "pass_err") == 0 and stat(err, "faults") == 0
    assert stat(err, "cap") == 1 and stat(err, "final_capped") == 1       # idle timeout parked the head
    assert stat(err, "max_speed") <= 18000 * 2                            # never above the head's fire-rate limit (counts/s)


def test_two_pages_in_one_job_reuse_swath_indices():
    """Second page restarts at swath idx 0: must print again (not be deduped), with its own uncap-free start."""
    img1 = make_image()
    img2 = img1.transpose(Image.FLIP_LEFT_RIGHT)                          # different content: a skipped page 2 would show
    frames = list(frames_for_image(img1)) + list(frames_for_image(img2))
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "o.pbm")
        s = Sim(out)
        send_frames(iter(frames), s.write, s.read_frame)
        rc, err = s.finish()
        assert rc == 0, err
        assert stat(err, "passes") == 48 and stat(err, "uncap") == 1 and stat(err, "wipe") == 2
        assert stat(err, "pass_err") == 0 and stat(err, "dups") == 0
        assert np.array_equal(read_pbm(out), expected(img2)) and not np.array_equal(expected(img1), expected(img2))


def test_bidirectional_lag_needs_offset_correction():
    img = make_image(); want = expected(img)
    good, rc, err = print_page(img, lag=1, bidir=2)          # correct calibration: reverse offset = 2*lag
    assert rc == 0, err and np.array_equal(good, want)
    bad, rc, err = print_page(img, lag=1, bidir=0)           # uncorrected: odd (leftward) swaths shift a dot
    assert rc == 0 and not np.array_equal(bad, want)
    diff_rows = np.nonzero((bad != want).any(axis=1))[0]
    assert set((diff_rows // 150) % 2) == {1}                # only leftward swaths are wrong


def test_lossy_link_still_prints_exact_page():
    img = make_image()
    state = {"n": 0, "flips": 0, "truncs": 0}

    def mangle(write):
        def w(b):
            state["n"] += 1
            k = state["n"]
            if k % 40 == 7:                                   # payload bit flip -> CRC error -> no reply -> retransmit
                b = bytearray(b); b[len(b) // 2] ^= 0x10; b = bytes(b); state["flips"] += 1
            elif k % 97 == 11:                                # truncated frame -> parser stalls -> sim timeout reset
                b = b[:-2]; state["truncs"] += 1
            write(b)
        return w
    got, rc, err = print_page(img, mangle=mangle)
    assert rc == 0, err
    assert np.array_equal(got, expected(img))
    crc_err = int(err.split("crc_err=")[1].split()[0])
    assert state["flips"] > 5 and state["truncs"] > 5         # both fault types really were injected
    assert crc_err >= state["flips"]                          # every bit flip was rejected by the device CRC
    assert "passes=24" in err                                 # and each swath still printed exactly once (idempotent)


def test_nak_forever_and_stale_flood_are_bounded():
    f = frames_for_image(make_image())
    first = next(f)
    with pytest.raises(LinkError):                            # device NAKs every frame
        send_frames([first], lambda b: None, lambda: (p.T_NAK, struct.pack("<H", p.frame_crc(first))), retries=3)
    with pytest.raises(LinkError):                            # device floods replies for OTHER frames faster than the timeout
        send_frames([first], lambda b: None, lambda: (p.T_ACK, b"\x00\x00"), retries=2)


def test_dead_link_raises():
    with tempfile.TemporaryDirectory() as d:
        s = Sim(os.path.join(d, "o.pbm"))
        with pytest.raises(LinkError):
            send_frames(frames_for_image(make_image()), lambda b: None, s.read_frame, retries=1)
        s.finish()
