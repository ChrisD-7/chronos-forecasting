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


def test_device_uri_parsing():
    assert cups.parse_device_uri("openinkjet:/dev/ttyACM0") == "/dev/ttyACM0"
    for bad in ("", "http://x", "openinkjet:relative", "openinkjet:/etc/passwd", "openinkjet:/dev/../etc/passwd",
                "openinkjet:/dev/sda", "openinkjet:/dev/null", "openinkjet:/dev/tty"):
        with pytest.raises(ValueError):
            cups.parse_device_uri(bad)


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
    assert cups.backend_main(args, environ={"DEVICE_URI": "openinkjet:/dev/ttyACM77"}, stdin=io.BytesIO(good)) == cups.CUPS_BACKEND_RETRY  # device missing -> retry
    assert cups.backend_main(args, environ={"DEVICE_URI": "openinkjet:/dev/ttyACM0"}, stdin=io.BytesIO(good[:-3])) == cups.CUPS_BACKEND_FAILED  # truncated job
    assert (cups.CUPS_BACKEND_FAILED, cups.CUPS_BACKEND_STOP, cups.CUPS_BACKEND_RETRY) == (1, 4, 6)     # values from cups/backend.h


def test_fdlink_roundtrip_and_timeout():
    r1, w1 = os.pipe(); r2, w2 = os.pipe()
    a, b = FdLink(r1, w2, timeout=0.05), FdLink(r2, w1, timeout=0.05)
    assert a.read_frame() is None                          # nothing yet: times out
    b.write(p.encode(p.T_ACK, b"\x01\x02") + b"\x00garbage" + p.encode(p.T_NAK, b"\x03\x04"))
    assert a.read_frame() == (p.T_ACK, b"\x01\x02")
    assert a.read_frame() == (p.T_NAK, b"\x03\x04")       # garbage between frames is skipped
    for fd in (r1, w1, r2, w2): os.close(fd)


def test_backend_over_pty_to_real_firmware_sim(tmp_path):
    """Backend -> pty -> C simulator (real job controller): the whole page is ACKed and printed."""
    import pty, tty, subprocess
    sys.path.insert(0, os.path.dirname(__file__))
    import test_e2e_sim as e2e
    src = ["tests/sim.c"] + [f"core/{n}.c" for n in ("oi_job", "oi_proto", "oi_sched", "oi_head_matrix", "oi_motion")]
    sim = str(tmp_path / "oi_sim")
    subprocess.run(["gcc", "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-o", sim] + src,
                   cwd=e2e.FW, check=True)
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
            assert mime in ('image/png', 'image/x-portable-bitmap'), mime      # types that exist in CUPS mime.types
