# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
import io, os, struct, sys, subprocess, tempfile, pytest
from PIL import Image
from openinkjet import cups, protocol as p
from openinkjet.link import FdLink
from openinkjet.filter import frames_for_image
from openinkjet.sender import send_frames


def png_bytes():
    b = io.BytesIO(); Image.new("L", (30, 30), 60).save(b, "PNG"); return b.getvalue()


def test_filter_stdin_and_file_produce_identical_frames(tmp_path):
    out1, out2 = io.BytesIO(), io.BytesIO()
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(png_bytes()), stdout=out1) == 0
    f = tmp_path / "a.png"; f.write_bytes(png_bytes())
    assert cups.filter_main(["f", "1", "u", "t", "1", "", str(f)], stdout=out2) == 0
    assert out1.getvalue() == out2.getvalue() and len(out1.getvalue()) > 1000
    n = 0; buf = out1.getvalue()
    while buf:
        _, _, c = p.decode(buf); buf = buf[c:]; n += 1
    assert n > 24 * 3


def test_filter_rejects_bad_args_and_bad_image(capsys):
    assert cups.filter_main(["f", "1"], stdout=io.BytesIO()) == 1
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(b"not an image"), stdout=io.BytesIO()) == 1


def test_device_uri_parsing_production_rules(monkeypatch):
    monkeypatch.setattr(cups, "_pty_allowed", lambda: False)
    assert cups.parse_device_uri("openinkjet:/dev/ttyACM0") == "/dev/ttyACM0"
    assert cups.parse_device_uri("openinkjet:/dev/ttyUSB12") == "/dev/ttyUSB12"
    for bad in ("", "http://x", "openinkjet:relative", "openinkjet:/etc/passwd", "openinkjet:/dev/../etc/passwd", "openinkjet:/dev/sda",
                "openinkjet:/dev/null", "openinkjet:/dev/tty", "openinkjet:/dev/ttyACMfoo", "openinkjet:/dev/ttyACM", "openinkjet:/dev/ttyACM0x",
                "openinkjet:/dev/pts/0", "openinkjet:/dev/pts/ptmx", "openinkjet:/dev/ttyS0"):
        with pytest.raises(ValueError):
            cups.parse_device_uri(bad)


def test_pty_only_with_root_owned_opt_in(monkeypatch, tmp_path):
    assert cups.parse_device_uri("openinkjet:/dev/ttyACM0") == "/dev/ttyACM0"
    monkeypatch.setattr(cups, "_pty_allowed", lambda: True)
    assert cups.parse_device_uri("openinkjet:/dev/pts/3") == "/dev/pts/3"
    with pytest.raises(ValueError):
        cups.parse_device_uri("openinkjet:/dev/pts/ptmx")                       # not a numbered pty, even with the opt-in
    f = tmp_path / "allow_pty"; f.write_text("x")
    monkeypatch.undo(); monkeypatch.setattr(cups, "ALLOW_PTY_FILE", str(f))
    os.chmod(f, 0o666)
    assert cups._pty_allowed() is False                                          # world-writable opt-in is rejected
    os.chmod(f, 0o644)
    assert cups._pty_allowed() == (os.geteuid() == 0)                            # accepted only when owned by root (this test may run unprivileged)


def test_device_uri_symlink_escape_rejected(tmp_path):
    link = tmp_path / "ttyACM9"; link.symlink_to("/etc/passwd")
    with pytest.raises(ValueError):
        cups.parse_device_uri("openinkjet:" + str(link))


def test_backend_discovery_lists_only_existing_devices(capsys, monkeypatch):
    monkeypatch.setattr(cups.glob, "glob", lambda pat: [])
    assert cups.backend_main(["openinkjet"]) == 0 and capsys.readouterr().out == ""
    monkeypatch.setattr(cups.glob, "glob", lambda pat: ["/dev/ttyACM1", "/dev/ttyACM0"])
    assert cups.backend_main(["openinkjet"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [l.split()[1] for l in lines] == ["openinkjet:/dev/ttyACM0", "openinkjet:/dev/ttyACM1"]


def test_backend_error_paths(capsys):
    good = b"".join(p.encode(p.T_START_PASS, b"\x00\x00") for _ in range(2))
    args = ["openinkjet", "1", "u", "t", "1", ""]
    assert cups.backend_main(args, environ={"DEVICE_URI": "http://x"}, stdin=io.BytesIO(good)) == cups.CUPS_BACKEND_STOP
    assert cups.backend_main(args, environ={"DEVICE_URI": "openinkjet:/dev/ttyACM77"}, stdin=io.BytesIO(good)) == cups.CUPS_BACKEND_STOP   # device missing: stop the queue
    assert cups.backend_main(args, environ={"DEVICE_URI": "openinkjet:/dev/ttyACM0"}, stdin=io.BytesIO(good[:-3])) == cups.CUPS_BACKEND_CANCEL  # truncated job: cancel it
    assert (cups.CUPS_BACKEND_FAILED, cups.CUPS_BACKEND_STOP, cups.CUPS_BACKEND_CANCEL, cups.CUPS_BACKEND_RETRY) == (1, 4, 5, 6)   # values from cups/backend.h


def test_fdlink_roundtrip_and_timeout():
    r1, w1 = os.pipe(); r2, w2 = os.pipe()
    a, b = FdLink(r1, w2, timeout=0.05), FdLink(r2, w1, timeout=0.05)
    assert a.read_frame() is None                          # nothing yet: times out
    b.write(p.encode(p.T_ACK, b"\x01\x02") + b"\x00garbage" + p.encode(p.T_NAK, b"\x03\x04"))
    assert a.read_frame() == (p.T_ACK, b"\x01\x02")
    assert a.read_frame() == (p.T_NAK, b"\x03\x04")       # garbage between frames is skipped
    for fd in (r1, w1, r2, w2): os.close(fd)


@pytest.mark.parametrize("ftype,payload", [
    (p.T_ACK, b"\x00\x00"), (p.T_ERROR, b"\x01\x00\x00\x00"), (p.T_BUSY, b"\x00\x00"), (77, b""),                              # device-only / unknown types
    (p.T_SWATH_HDR, struct.pack("<HIHbI", 0, 100000, 1, 1, 12700)),                                                        # columns out of range
    (p.T_SWATH_HDR, struct.pack("<HIHbI", 0, 100, 0, 1, 12700)), (p.T_SWATH_HDR, struct.pack("<HIHbI", 0, 100, 1, 0, 12700)),
    (p.T_SWATH_HDR, struct.pack("<HIHbI", 0, 100, 1, 1, 10_000_000)), (p.T_SWATH_HDR, b"\x00" * 12),                         # feed too long / short header
    (p.T_SWATH_DATA, b"\x00\x00"), (p.T_SWATH_DATA, struct.pack("<I", 0xFFFFFFFF) + b"x"),
    (p.T_START_PASS, b""), (p.T_PAGE_END, b"x"), (p.T_RESET, b"x")])
def test_validate_frame_rejects_untrusted_content(ftype, payload):
    assert p.validate_frame(ftype, payload) is not None


def test_validate_frame_accepts_what_the_filter_produces():
    import io
    out = io.BytesIO()
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(png_bytes()), stdout=out) == 0
    buf = out.getvalue()
    while buf:
        t_, pl, n = p.decode(buf); buf = buf[n:]
        assert p.validate_frame(t_, pl) is None
    assert p.validate_frame(p.T_RESET, b"") is None


def test_raw_bad_job_is_cancelled_not_sent(monkeypatch):
    """CUPS lets any user submit RAW jobs to the root backend: a bad stream must cancel only that job (exit 5), never open the device."""
    opened = []
    monkeypatch.setattr(cups, "open_serial", lambda path: opened.append(path))
    bad = p.encode(p.T_SWATH_HDR, struct.pack("<HIHbI", 0, 100000, 1, 1, 12700))
    assert cups.backend_main(["o", "1", "u", "t", "1", ""], environ={"DEVICE_URI": "openinkjet:/dev/ttyACM0"}, stdin=io.BytesIO(bad)) == cups.CUPS_BACKEND_CANCEL
    assert opened == []


def test_filter_honours_copies_and_clamps():
    one, three, huge = io.BytesIO(), io.BytesIO(), io.BytesIO()
    cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(png_bytes()), stdout=one)
    cups.filter_main(["f", "1", "u", "t", "3", ""], stdin=io.BytesIO(png_bytes()), stdout=three)
    cups.filter_main(["f", "1", "u", "t", "100000", ""], stdin=io.BytesIO(png_bytes()), stdout=huge)
    assert len(three.getvalue()) == 3 * len(one.getvalue()) and len(huge.getvalue()) == cups.MAX_COPIES * len(one.getvalue())
    junk = io.BytesIO()
    cups.filter_main(["f", "1", "u", "t", "abc", ""], stdin=io.BytesIO(png_bytes()), stdout=junk)
    assert junk.getvalue() == one.getvalue()                                    # unparsable copies = 1


def test_filter_rejects_decompression_bombs_quickly():
    import time
    big = io.BytesIO(); Image.new("L", (12000, 12000), 7).save(big, "PNG")        # 144 Mpixel but a tiny file
    t0 = time.time()
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(big.getvalue()), stdout=io.BytesIO()) == 1
    assert time.time() - t0 < 5
    thin = io.BytesIO(); Image.new("L", (1, 60_000_000), 7).save(thin, "PNG")      # 60 Mpixel: between 1x and 2x the limit, where PIL only warns
    err = io.StringIO(); monkeypatch_stderr = sys.stderr; sys.stderr = err
    try:
        rc = cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(thin.getvalue()), stdout=io.BytesIO())
    finally:
        sys.stderr = monkeypatch_stderr
    assert rc == 1 and "too large" in err.getvalue()


def test_open_serial_restores_the_tty_on_close():
    import pty, termios
    from openinkjet.link import open_serial
    master, slave = pty.openpty()
    before = termios.tcgetattr(slave)
    link = open_serial(os.ttyname(slave))
    assert termios.tcgetattr(slave)[3] != before[3]                              # raw mode while open
    link.close()
    assert termios.tcgetattr(slave) == before                                    # put back exactly as found
    os.close(master); os.close(slave)


def test_backend_sends_reset_when_the_link_gives_up(monkeypatch):
    sent = []
    class FakeLink:
        def write(self, b): sent.append(b)
        def read_frame(self): return None
        def close(self): sent.append("closed")
    monkeypatch.setattr(cups, "open_serial", lambda path: FakeLink())
    monkeypatch.setattr(cups, "parse_device_uri", lambda uri: "/dev/ttyACM0")
    monkeypatch.setattr(cups, "send_frames", lambda *a, **k: (_ for _ in ()).throw(cups.LinkError("no ack")))
    job = p.encode(p.T_PAGE_END)
    rc = cups.backend_main(["o", "1", "u", "t", "1", ""], environ={"DEVICE_URI": "x"}, stdin=io.BytesIO(job))
    assert rc == cups.CUPS_BACKEND_RETRY and p.encode(p.T_RESET) in sent and sent[-1] == "closed"


def test_backend_over_pty_to_real_firmware_sim(tmp_path, monkeypatch):
    """Backend -> pty -> C simulator (real job controller): the whole page is ACKed and printed."""
    import pty, tty, subprocess
    sys.path.insert(0, os.path.dirname(__file__))
    import test_e2e_sim as e2e
    src = ["tests/sim.c"] + [f"core/{n}.c" for n in ("oi_app", "oi_job", "oi_proto", "oi_sched", "oi_head_matrix", "oi_motion", "oi_maint")]
    sim = str(tmp_path / "oi_sim")
    subprocess.run(["gcc", "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-o", sim] + src,
                   cwd=e2e.FW, check=True)
    monkeypatch.setattr(cups, "_pty_allowed", lambda: True)                      # production refuses /dev/pts; the test opts in
    master, slave = pty.openpty(); tty.setraw(master); tty.setraw(slave)
    out = tmp_path / "o.pbm"
    proc = subprocess.Popen([sim, str(out)], stdin=master, stdout=master, stderr=subprocess.PIPE)
    dev = os.ttyname(slave)
    stream = b"".join(frames_for_image(e2e.make_image()))
    jobfile = tmp_path / "job.bin"; jobfile.write_bytes(stream)
    rc = cups.backend_main(["openinkjet", "1", "u", "t", "1", "", str(jobfile)], environ={"DEVICE_URI": "openinkjet:" + dev})
    assert rc == cups.CUPS_BACKEND_OK
    os.close(slave)                                    # backend closed its side; end the sim by closing the master
    os.close(master)
    err = proc.stderr.read().decode(); proc.wait(timeout=30)
    assert "passes=24" in err
    got = e2e.read_pbm(str(out))
    assert (got == e2e.expected(e2e.make_image())).all()


def test_ppd_is_wellformed():
    path = os.path.join(os.path.dirname(__file__), "..", "cups", "openinkjet.ppd")
    text = open(path).read()
    assert text.startswith('*PPD-Adobe: "4.3"') and "*cupsFilter:" in text
    opens = text.count("*OpenUI"); closes = text.count("*CloseUI")
    assert opens == closes == 3
    for line in text.splitlines():
        if line.startswith('*cupsFilter:'):
            mime = line.split('"')[1].split()[0]
            assert mime in ('image/png', 'image/x-portable-bitmap', 'application/pdf'), mime      # types that exist in CUPS mime.types


def _pdf_bytes(pages=2):
    imgs = [Image.new("L", (595, 842), 255 if k % 2 == 0 else 0) for k in range(pages)]
    buf = io.BytesIO(); imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:], resolution=72.0)
    return buf.getvalue()


def _page_ends(stream: bytes):
    n = off = 0
    while off < len(stream):
        t_, pl, c = p.decode(stream, off); off += c
        n += t_ == p.T_PAGE_END
    return n


@pytest.mark.skipif(__import__("shutil").which("pdftoppm") is None, reason="needs poppler-utils")
def test_filter_rasterises_a_multipage_pdf():
    out = io.BytesIO()
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(_pdf_bytes(3)), stdout=out) == 0
    assert _page_ends(out.getvalue()) == 3                                       # one page of frames per PDF page
    two = io.BytesIO()
    cups.filter_main(["f", "1", "u", "t", "2", ""], stdin=io.BytesIO(_pdf_bytes(1)), stdout=two)
    assert _page_ends(two.getvalue()) == 2                                       # copies apply to PDFs too


@pytest.mark.skipif(__import__("shutil").which("pdftoppm") is None, reason="needs poppler-utils")
def test_pdf_hostile_inputs_fail_cleanly_and_fast():
    import time
    t0 = time.time()
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(b"%PDF-1.4\n garbage"), stdout=io.BytesIO()) == 1
    huge = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 14400 14400]>>endobj\ntrailer<</Root 1 0 R/Size 4>>\n%%EOF\n")
    out = io.BytesIO()
    rc = cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(huge), stdout=out)   # 200 x 200 inch page: poppler clamps it
    assert rc in (0, 1) and len(out.getvalue()) < 10_000_000                                  # either rejected or bounded to one fitted page
    many = io.BytesIO(); imgs = [Image.new("L", (60, 80), 255) for _ in range(120)]
    imgs[0].save(many, "PDF", save_all=True, append_images=imgs[1:], resolution=72.0)
    capped = io.BytesIO()
    assert cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(many.getvalue()), stdout=capped) == 0
    assert _page_ends(capped.getvalue()) == cups.MAX_PDF_PAGES                                  # 120-page PDF is cut at the page cap
    assert time.time() - t0 < 120


def test_orientation_options_rotate_the_page():
    wide = Image.new("L", (400, 100), 255); wide.paste(0, (0, 0, 100, 100))          # black square at the left
    b = io.BytesIO(); wide.save(b, "PNG")
    port, land = io.BytesIO(), io.BytesIO()
    cups.filter_main(["f", "1", "u", "t", "1", ""], stdin=io.BytesIO(b.getvalue()), stdout=port)
    cups.filter_main(["f", "1", "u", "t", "1", "orientation-requested=4"], stdin=io.BytesIO(b.getvalue()), stdout=land)
    assert port.getvalue() != land.getvalue()
    assert cups._orientation_degrees("orientation-requested=5 copies=2") == 270
    assert cups._orientation_degrees("landscape") == 90 and cups._orientation_degrees("landscape=false") == 0
    assert cups._orientation_degrees("orientation-requested=3") == 0 and cups._orientation_degrees("") == 0


def test_decode_with_offset_matches_slicing_and_is_linear():
    import time
    frames = [p.encode(p.T_START_PASS, struct.pack("<H", k % 65535)) for k in range(20000)]
    stream = b"".join(frames)
    off = 0
    for k, f in enumerate(frames[:200]):
        t_, pl, n = p.decode(stream, off)
        assert (t_, pl, n) == p.decode(stream[off:]) and n == len(f)
        off += n
    t0 = time.time(); off = 0; count = 0
    while off < len(stream):
        _, _, n = p.decode(stream, off); off += n; count += 1
    assert count == 20000 and time.time() - t0 < 2.0                                   # 20000 frames scanned without copying the stream
    with pytest.raises(p.NeedMore):
        p.decode(stream[:10], 8)
    with pytest.raises(ValueError):
        p.decode(b"\x00\xa5\x03\x02\x00\x00\x00\x00\x00", 0)
