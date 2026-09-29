"""End-to-end: host filter -> frames -> REAL C firmware core in a simulated printer -> printed page == input bitmap."""
import os, select, struct, subprocess, tempfile
import numpy as np
import pytest
from PIL import Image
from openinkjet import protocol as p
from openinkjet.filter import frames_for_image, page_bitmap
from openinkjet.sender import send_frames, LinkError

FW = os.path.join(os.path.dirname(__file__), "..", "..", "firmware")
SIM = "/tmp/oi_sim"


@pytest.fixture(scope="session", autouse=True)
def build_sim():
    src = ["tests/sim.c"] + [f"core/{n}.c" for n in ("oi_job", "oi_proto", "oi_sched", "oi_head_matrix", "oi_motion")]
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
    state = {"n": 0}

    def mangle(write):
        def w(b):
            state["n"] += 1
            k = state["n"]
            if k % 40 == 7:                                   # payload bit flip -> CRC error -> no reply -> retransmit
                b = bytearray(b); b[len(b) // 2] ^= 0x10; b = bytes(b)
            elif k % 97 == 11:                                # truncated frame -> parser stalls -> sim timeout reset
                b = b[:-2]
            write(b)
        return w
    got, rc, err = print_page(img, mangle=mangle)
    assert rc == 0, err
    assert np.array_equal(got, expected(img))
    crc_err = int(err.split("crc_err=")[1].split()[0])
    assert crc_err > 0                                        # the corruption really happened


def test_dead_link_raises():
    with tempfile.TemporaryDirectory() as d:
        s = Sim(os.path.join(d, "o.pbm"))
        with pytest.raises(LinkError):
            send_frames(frames_for_image(make_image()), lambda b: None, s.read_frame, retries=1)
        s.finish()
