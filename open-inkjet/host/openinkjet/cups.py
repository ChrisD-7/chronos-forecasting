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
PDF_MAX_PAGE_FILE_BYTES = 256 * 1024 * 1024    # one rendered page PNG may not exceed this (RLIMIT_FSIZE)
MAX_JOB_BYTES = 300 * 1024 * 1024              # backend: cap on a whole job stream (a 50-page job is about 115 MB)


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


def _limits():
    """Child limits for pdftoppm: address space, per-file size, and death with the parent (CUPS cancels a job with SIGTERM)."""
    import ctypes, resource, signal
    resource.setrlimit(resource.RLIMIT_AS, (PDFTOPPM_MEM_BYTES, PDFTOPPM_MEM_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (PDF_MAX_PAGE_FILE_BYTES, PDF_MAX_PAGE_FILE_BYTES))
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)       # PR_SET_PDEATHSIG: never outlive the filter
    except Exception:
        pass


def _run_poppler(argv, timeout):
    import subprocess
    return subprocess.run(argv, capture_output=True, timeout=timeout, preexec_fn=_limits, env={"PATH": "/usr/bin:/bin"})


def _pdf_page_count(exe_info, path):
    """Pages according to pdfinfo, or None if pdfinfo is unavailable or fails."""
    if not exe_info:
        return None
    try:
        r = _run_poppler([exe_info, path], 30)
    except Exception:
        return None
    m = re.search(rb"^Pages:\s+(\d+)", r.stdout, re.M)
    return int(m.group(1)) if r.returncode == 0 and m else None


def _pdf_pages(data: bytes):
    """Rasterise a PDF to greyscale page images with pdftoppm (poppler), ONE PAGE AT A TIME in a throwaway directory so disk use is bounded
    by a single page, with time, memory and file-size limits and a sanitised environment. Yields PIL images; raises RuntimeError on any
    problem: too many pages (never silently truncated), blank/degenerate render, timeout."""
    import shutil, subprocess, tempfile
    exe, info = shutil.which("pdftoppm"), shutil.which("pdfinfo")
    if not exe:
        raise RuntimeError("pdftoppm (poppler-utils) is not installed")
    with tempfile.TemporaryDirectory(prefix="oi-pdf-") as d:
        src = os.path.join(d, "in.pdf")
        with open(src, "wb") as fh:
            fh.write(data)
        total = _pdf_page_count(info, src)
        if total is not None and total > MAX_PDF_PAGES:
            raise RuntimeError("PDF has %d pages; the limit is %d (not truncating silently)" % (total, MAX_PDF_PAGES))
        n_pages = total if total is not None else MAX_PDF_PAGES
        for n in range(1, n_pages + 1):
            out = os.path.join(d, "pg")
            try:
                r = _run_poppler([exe, "-r", str(PDF_DPI), "-gray", "-png", "-f", str(n), "-l", str(n), "-singlefile", src, out], PDFTOPPM_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                raise RuntimeError("pdftoppm timed out after %d s on page %d" % (PDFTOPPM_TIMEOUT_S, n))
            png = out + ".png"
            if r.returncode or not os.path.exists(png):
                if total is None and n > 1:
                    return                                         # pdfinfo unavailable: ran past the last page
                raise RuntimeError("pdftoppm failed on page %d: %s" % (n, r.stderr.decode("latin1", "replace")[:200]))
            img = Image.open(png)
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise RuntimeError("PDF page %d too large (%dx%d px)" % (n, img.width, img.height))
            if img.width < 16 or img.height < 16:                  # poppler writes a 1x1 page for a bogus/oversized MediaBox and exits 0
                raise RuntimeError("PDF page %d rendered as %dx%d px (oversized or invalid page size): %s" %
                                   (n, img.width, img.height, r.stderr.decode("latin1", "replace")[:120]))
            img.load()
            os.remove(png)
            yield img


def _is_pdf(data: bytes) -> bool:
    return data[:1024].find(b"%PDF-") >= 0                         # the spec allows junk before the header within the first 1024 bytes


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
    import signal
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))   # CUPS cancels a job with SIGTERM: unwind so temp files go and pdftoppm is killed
    except ValueError:
        pass                                                      # not the main thread (tests)
    try:
        if len(argv) == 7:
            with open(argv[6], "rb") as fh:
                data = fh.read(MAX_INPUT_BYTES + 1)
        else:
            data = (stdin or sys.stdin.buffer).read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise RuntimeError("input larger than %d MB" % (MAX_INPUT_BYTES >> 20))
        frames = []
        is_pdf = _is_pdf(data)
        if is_pdf:
            images = _pdf_pages(data)
        else:
            img = Image.open(io.BytesIO(data))                      # lazy: reads the header only
            if img.width * img.height > MAX_IMAGE_PIXELS:           # explicit, not just PIL's warn-then-error behaviour
                raise Image.DecompressionBombError("%dx%d pixels" % (img.width, img.height))
            img.load()
            images = [img]
        for img in images:
            if rotate and not is_pdf:                            # CUPS (texttopdf/pdftopdf) already applies orientation to documents it turns into PDF
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
                data = fh.read(MAX_JOB_BYTES + 1)
        else:
            data = (stdin or sys.stdin.buffer).read(MAX_JOB_BYTES + 1)
        if len(data) > MAX_JOB_BYTES:
            raise ValueError("job larger than %d MB" % (MAX_JOB_BYTES >> 20))
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
