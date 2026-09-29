# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""CUPS entry points. UNTESTED against a real CUPS install (none in the build sandbox); exit codes checked
against OpenPrinting/cups backend.h; argument conventions follow the CUPS filter/backend contract:
argv = job user title copies options [file].
- filter_main():  image (file or stdin) -> protocol frames on stdout.
- backend_main(): frames (file or stdin) -> device named by DEVICE_URI 'openinkjet:/dev/ttyACM0'.
Installed as executables by host/install_cups.sh (see host/bin/)."""
import glob, os, sys, termios
from PIL import Image
from .filter import frames_for_image
from . import protocol as p
from .link import open_serial
from .sender import send_frames, LinkError

# CUPS backend exit codes (cups/backend.h)
CUPS_BACKEND_OK, CUPS_BACKEND_FAILED, CUPS_BACKEND_STOP, CUPS_BACKEND_RETRY = 0, 1, 4, 6
ALLOWED_PREFIXES = ("/dev/ttyACM", "/dev/ttyUSB", "/dev/pts/")     # /dev/pts allows the pty-based test


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
    try:
        for f in frames_for_image(img):
            out.write(f)
        out.flush()
    except BrokenPipeError:
        return 1
    return 0


def parse_device_uri(uri: str) -> str:
    """openinkjet:/dev/ttyACM0 -> validated real path. Rejects traversal, symlinks to elsewhere and non-tty names."""
    if not uri.startswith("openinkjet:"):
        raise ValueError("unsupported DEVICE_URI: %r" % uri)
    path = uri[len("openinkjet:"):]
    real = os.path.realpath(path)                    # resolves .. and symlinks before the prefix check
    if not real.startswith(ALLOWED_PREFIXES):
        raise ValueError("device %r resolves to %r, which is not an allowed tty path" % (path, real))
    return real


def _frames_from(data: bytes):
    frames, off = [], 0
    while off < len(data):
        _, _, n = p.decode(data[off:])               # raises ValueError on a corrupt/truncated stream
        frames.append(data[off:off + n])
        off += n
    return frames


def backend_main(argv=None, environ=None, stdin=None):
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    if len(argv) == 1:                               # CUPS device discovery: only devices that exist
        for dev in sorted(glob.glob("/dev/ttyACM*")):
            print('direct openinkjet:%s "Open Inkjet" "Open Inkjet USB serial" "MFG:Open Inkjet;MDL:A4;"' % dev)
        return CUPS_BACKEND_OK
    if len(argv) not in (6, 7):
        sys.stderr.write("ERROR: usage: openinkjet job user title copies options [file]\n")
        return CUPS_BACKEND_FAILED
    try:                                             # validate the job before touching the device
        if len(argv) == 7:
            with open(argv[6], "rb") as fh:
                data = fh.read()
        else:
            data = (stdin or sys.stdin.buffer).read()
        frames = _frames_from(data)
    except (ValueError, OSError) as e:
        sys.stderr.write("ERROR: unusable job stream: %s\n" % e)
        return CUPS_BACKEND_FAILED
    try:
        dev = parse_device_uri(environ.get("DEVICE_URI", ""))
    except ValueError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return CUPS_BACKEND_STOP                     # misconfigured queue: stop it rather than retry forever
    link = None
    try:
        link = open_serial(dev)
        send_frames(frames, link.write, link.read_frame)
    except (OSError, termios.error) as e:
        sys.stderr.write("ERROR: cannot open %s: %s\n" % (dev, e))
        return CUPS_BACKEND_RETRY
    except LinkError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return CUPS_BACKEND_RETRY
    finally:
        if link:
            link.close()
    return CUPS_BACKEND_OK
