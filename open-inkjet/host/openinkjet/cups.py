"""CUPS entry points. UNTESTED against a real CUPS install (none in the build sandbox); argument
conventions follow the CUPS filter/backend contract: argv = job user title copies options [file].
- filter():  image (file or stdin) -> protocol frames on stdout.
- backend(): frames (file or stdin) -> device named by DEVICE_URI 'openinkjet:/dev/ttyACM0'."""
import os, sys
from PIL import Image
from .filter import frames_for_image
from .link import open_serial
from .sender import send_frames, LinkError

EX_TEMPFAIL = 1   # CUPS: retry the job


def filter_main(argv=None, stdin=None, stdout=None):
    argv = sys.argv if argv is None else argv
    if len(argv) not in (6, 7):
        sys.stderr.write("ERROR: usage: oi_filter job user title copies options [file]\n")
        return 1
    src = argv[6] if len(argv) == 7 else (stdin or sys.stdin.buffer)
    out = stdout or sys.stdout.buffer
    try:
        img = Image.open(src)
        img.load()
    except Exception as e:
        sys.stderr.write("ERROR: cannot read page image: %s\n" % e)
        return 1
    for f in frames_for_image(img):
        out.write(f)
    out.flush()
    return 0


def parse_device_uri(uri: str) -> str:
    if not uri.startswith("openinkjet:"):
        raise ValueError("unsupported DEVICE_URI: %r" % uri)
    path = uri[len("openinkjet:"):]
    if not path.startswith("/dev/"):
        raise ValueError("device path must be under /dev/: %r" % path)
    return path


def backend_main(argv=None, environ=None, stdin=None):
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    if len(argv) == 1:                                      # CUPS device discovery
        print('direct openinkjet:/dev/ttyACM0 "Open Inkjet" "Open Inkjet USB serial"')
        return 0
    if len(argv) not in (6, 7):
        sys.stderr.write("ERROR: usage: openinkjet job user title copies options [file]\n")
        return 1
    try:
        dev = parse_device_uri(environ.get("DEVICE_URI", ""))
        link = open_serial(dev)
    except (ValueError, OSError) as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return EX_TEMPFAIL
    data = open(argv[6], "rb").read() if len(argv) == 7 else (stdin or sys.stdin.buffer).read()
    from . import protocol as p
    frames, off = [], 0
    while off < len(data):
        try:
            _, _, n = p.decode(data[off:])
        except ValueError as e:
            sys.stderr.write("ERROR: corrupt frame stream at byte %d: %s\n" % (off, e))
            return 1
        frames.append(data[off:off + n]); off += n
    try:
        send_frames(frames, link.write, link.read_frame)
    except LinkError:
        sys.stderr.write("ERROR: printer did not acknowledge\n")
        return EX_TEMPFAIL
    return 0
