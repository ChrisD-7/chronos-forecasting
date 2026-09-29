import io, os, struct, sys, subprocess, tempfile, pytest
from PIL import Image
from openinkjet import cups, protocol as p
from openinkjet.link import FdLink
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
    for bad in ("", "http://x", "openinkjet:relative", "openinkjet:/etc/passwd"):
        with pytest.raises(ValueError):
            cups.parse_device_uri(bad)


def test_backend_discovery_and_bad_uri(capsys):
    assert cups.backend_main(["openinkjet"]) == 0
    assert "openinkjet:/dev/ttyACM0" in capsys.readouterr().out
    assert cups.backend_main(["openinkjet", "1", "u", "t", "1", ""], environ={"DEVICE_URI": "http://x"}, stdin=io.BytesIO(b"")) == cups.EX_TEMPFAIL


def test_fdlink_roundtrip_and_timeout():
    r1, w1 = os.pipe(); r2, w2 = os.pipe()
    a, b = FdLink(r1, w2, timeout=0.05), FdLink(r2, w1, timeout=0.05)
    assert a.read_frame() is None                          # nothing yet: times out
    b.write(p.encode(p.T_ACK, b"\x01\x02") + b"\x00garbage" + p.encode(p.T_NAK, b"\x03\x04"))
    assert a.read_frame() == (p.T_ACK, b"\x01\x02")
    assert a.read_frame() == (p.T_NAK, b"\x03\x04")       # garbage between frames is skipped
    for fd in (r1, w1, r2, w2): os.close(fd)


def test_ppd_is_wellformed():
    path = os.path.join(os.path.dirname(__file__), "..", "cups", "openinkjet.ppd")
    text = open(path).read()
    assert text.startswith('*PPD-Adobe: "4.3"') and "*cupsFilter:" in text
    opens = text.count("*OpenUI"); closes = text.count("*CloseUI")
    assert opens == closes == 2
