# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""CUPS entry points. Tested end to end against CUPS 2.4.7 for direct PNG/PBM jobs (host/tests/cups_integration.py: lp -> cupsd ->
filter -> backend -> pty -> firmware simulator -> page bitmap), PPD checked with cupstestppd; exit codes checked against
OpenPrinting/cups backend.h; argument conventions follow the CUPS filter/backend contract: argv = job user title copies options [file].
- filter_main():  PNG/PBM image or PDF (file or stdin) -> protocol frames on stdout. Honours `copies` and orientation; media size, scaling
  and resolution options are ignored (every page is fitted to A4). PDF pages are rasterised with pdftoppm (poppler-utils) at 300 dpi.
- backend_main(): frames (file or stdin) -> device named by DEVICE_URI 'openinkjet:/dev/ttyACM0'. Runs as root, and CUPS lets any
  user submit RAW jobs straight to it, so the stream is treated as untrusted: only host->device frame types, with field bounds.
Installed as executables by host/install_cups.sh (see host/bin/)."""
import errno, glob, io, os, re, stat, sys, termios, warnings
from PIL import Image
from .filter import frames_for_image
from . import protocol as p
from .link import open_serial
from .sender import send_frames, LinkError

# CUPS backend exit codes (cups/backend.h)
CUPS_BACKEND_OK, CUPS_BACKEND_FAILED, CUPS_BACKEND_STOP, CUPS_BACKEND_CANCEL, CUPS_BACKEND_RETRY = 0, 1, 4, 5, 6
TTY_RE = re.compile(r"^/dev/tty(ACM|USB)[0-9]+$")
PTY_RE = re.compile(r"^/dev/pts/[0-9]+$")
ALLOW_PTY_FILE = "/etc/openinkjet/allow_pty"      # test-only opt-in: must exist, be owned by root and not group/world writable
MAX_COPIES = 99
MAX_IMAGE_PIXELS = 40_000_000                      # PIL default is 89M (warning only up to 179M): far too much for a filter

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
warnings.simplefilter("error", Image.DecompressionBombWarning)


def _pty_allowed():
    try:
        st = os.stat(ALLOW_PTY_FILE)
    except OSError:
        return False
    return st.st_uid == 0 and not (st.st_mode & (stat.S_IWGRP | stat.S_IWOTH))


MAX_INPUT_BYTES = 200 * 1024 * 1024
MAX_PDF_PAGES = 50
PDF_DPI = 300                      # matches the printer's 300 dpi; the page is then fitted to A4 like any image
PDFTOPPM_TIMEOUT_S = 180
PDFTOPPM_MEM_BYTES = 2 * 1024 ** 3


def _orientation_degrees(options: str) -> int:
    """Counter-clockwise rotation for CUPS orientation options: orientation-requested 3 portrait, 4 landscape, 5 reverse landscape,
    6 reverse portrait; or the legacy `landscape` flag."""
    opts = {}
    for tok in options.split():
        k, _, v = tok.partition("=")
        opts[k] = v or "true"
    o = opts.get("orientation-requested")
    if o in ("4", "5", "6"):
        return {"4": 90, "5": 270, "6": 180}[o]
    if opts.get("landscape", "false").lower() in ("true", "yes", "on", "1"):
        return 90
    return 0


def _pdf_pages(data: bytes):
    """Rasterise a PDF to greyscale page images with pdftoppm (poppler) in a throwaway directory, with a time and memory limit.
    Yields PIL images; raises RuntimeError on failure."""
    import resource, shutil, subprocess, tempfile
    exe = shutil.which("pdftoppm")
    if not exe:
        raise RuntimeError("pdftoppm (poppler-utils) is not installed")
    with tempfile.TemporaryDirectory(prefix="oi-pdf-") as d:
        src = os.path.join(d, "in.pdf")
        with open(src, "wb") as fh:
            fh.write(data)

        def limits():
            resource.setrlimit(resource.RLIMIT_AS, (PDFTOPPM_MEM_BYTES, PDFTOPPM_MEM_BYTES))
        try:
            r = subprocess.run([exe, "-r", str(PDF_DPI), "-gray", "-png", "-f", "1", "-l", str(MAX_PDF_PAGES), src, os.path.join(d, "pg")],
                               capture_output=True, timeout=PDFTOPPM_TIMEOUT_S, preexec_fn=limits, env={"PATH": "/usr/bin:/bin"})
        except subprocess.TimeoutExpired:
            raise RuntimeError("pdftoppm timed out after %d s" % PDFTOPPM_TIMEOUT_S)
        if r.returncode:
            raise RuntimeError("pdftoppm failed: %s" % r.stderr.decode("latin1", "replace")[:200])
        pages = sorted(f for f in os.listdir(d) if f.startswith("pg") and f.endswith(".png"))
        if not pages:
            raise RuntimeError("PDF has no pages")
        for name in pages:
            img = Image.open(os.path.join(d, name))
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise RuntimeError("PDF page too large")
            img.load()
            yield img


def filter_main(argv=None, stdin=None, stdout=None):
    argv = sys.argv if argv is None else argv
    if len(argv) not in (6, 7):
        sys.stderr.write("ERROR: usage: oi_filter job user title copies options [file]\n")
        return 1
    try:
        copies = max(1, min(MAX_COPIES, int(argv[4])))
    except ValueError:
        copies = 1
    rotate = _orientation_degrees(argv[5])
    out = stdout or sys.stdout.buffer
    try:
        if len(argv) == 7:
            with open(argv[6], "rb") as fh:
                data = fh.read(MAX_INPUT_BYTES + 1)
        else:
            data = (stdin or sys.stdin.buffer).read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise RuntimeError("input larger than %d MB" % (MAX_INPUT_BYTES >> 20))
        frames = []
        if data[:5] == b"%PDF-":
            images = _pdf_pages(data)
        else:
            img = Image.open(io.BytesIO(data))                      # lazy: reads the header only
            if img.width * img.height > MAX_IMAGE_PIXELS:           # explicit, not just PIL's warn-then-error behaviour
                raise Image.DecompressionBombError("%dx%d pixels" % (img.width, img.height))
            img.load()
            images = [img]
        for img in images:
            if rotate:
                img = img.rotate(rotate, expand=True)
            frames.extend(frames_for_image(img))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, MemoryError) as e:
        sys.stderr.write("ERROR: image too large to process (limit %d pixels): %s\n" % (MAX_IMAGE_PIXELS, e))
        return 1
    except Exception as e:
        sys.stderr.write("ERROR: cannot read the job: %s\n" % e)
        return 1
    try:
        for _ in range(copies):
            for f in frames:
                out.write(f)
        out.flush()
    except BrokenPipeError:
        return 1
    return 0


def parse_device_uri(uri: str) -> str:
    """openinkjet:/dev/ttyACM0 -> validated real path. Production accepts only /dev/ttyACM<n> and /dev/ttyUSB<n> after resolving ..
    and symlinks; /dev/pts/<n> only if the root-owned opt-in file exists (used by the integration test)."""
    if not uri.startswith("openinkjet:"):
        raise ValueError("unsupported DEVICE_URI: %r" % uri)
    path = uri[len("openinkjet:"):]
    real = os.path.realpath(path)
    if TTY_RE.match(real) or (PTY_RE.match(real) and _pty_allowed()):
        return real
    raise ValueError("device %r resolves to %r, which is not an allowed tty path" % (path, real))


def _frames_from(data: bytes):
    """Split and validate a job stream. Raises ValueError with a reason for anything a well-behaved filter would not produce."""
    frames, off = [], 0
    while off < len(data):
        ftype, payload, n = p.decode(data, off)                # ValueError on a corrupt/truncated stream (no slicing: linear time)
        reason = p.validate_frame(ftype, payload)
        if reason:
            raise ValueError(reason)
        frames.append(data[off:off + n])
        off += n
    return frames


def backend_main(argv=None, environ=None, stdin=None):
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    if len(argv) == 1:                               # CUPS device discovery: only devices that exist
        for dev in sorted(glob.glob("/dev/ttyACM*")):
            if TTY_RE.match(dev):
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
        sys.stderr.write("ERROR: unusable job stream, job cancelled: %s\n" % e)
        return CUPS_BACKEND_CANCEL                   # cancel only this job: a bad raw job must not stop the whole queue
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
        # a missing/unreadable/non-tty device will not fix itself in 5 minutes: stop the queue; a busy device is worth retrying
        transient = isinstance(e, OSError) and e.errno in (errno.EBUSY, errno.EAGAIN, errno.EINTR)
        return CUPS_BACKEND_RETRY if transient else CUPS_BACKEND_STOP
    except LinkError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        try:                                         # best effort: tell the device to abandon the half-printed page so the retry starts clean
            link.write(p.encode(p.T_RESET))
            link.read_frame()
        except Exception:
            pass
        return CUPS_BACKEND_RETRY
    finally:
        if link:
            link.close()
    return CUPS_BACKEND_OK
