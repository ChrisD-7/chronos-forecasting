"""CLI filter: image (stdin or file) -> A4 bitmap at hdpi x vdpi -> halftone -> swath frames on stdout.
NOTE: not a CUPS raster filter yet (no PPD/backend); it is the pipeline core a CUPS wrapper would call."""
import argparse, sys
import numpy as np
from PIL import Image
from .heads import HP45
from .geometry import A4_MM, MM_PER_INCH
from .halftone import floyd_steinberg
from .slicer import slice_page, swath_feed_mm
from .protocol import swath_frames


MARGIN_MM = 4.0  # GUESS: unprintable border until measured on hardware


def _flatten(img: Image.Image) -> Image.Image:
    """Composite any transparency onto white before greyscale conversion."""
    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, rgba).convert("L")


def page_bitmap(img: Image.Image, hdpi: int, vdpi: int) -> np.ndarray:
    """Fit image inside the A4 printable area (aspect preserved, centred), white elsewhere."""
    w = round(A4_MM[0] / MM_PER_INCH * hdpi)
    h = round(A4_MM[1] / MM_PER_INCH * vdpi)
    mx = round(MARGIN_MM / MM_PER_INCH * hdpi)
    my = round(MARGIN_MM / MM_PER_INCH * vdpi)
    box_w, box_h = w - 2 * mx, h - 2 * my
    g = _flatten(img)
    sx, sy = box_w / g.width, box_h / g.height
    s = min(sx * 1.0, sy * 1.0)
    nw, nh = max(1, int(g.width * s)), max(1, int(g.height * s))
    g = g.resize((nw, nh), Image.LANCZOS)
    page = Image.new("L", (w, h), 255)
    page.paste(g, ((w - nw) // 2, (h - nh) // 2))
    return floyd_steinberg(np.asarray(page))


def pack_columns(swath: np.ndarray) -> bytes:
    """(columns, nozzles) 0/1 -> bytes, nozzle 0 in bit0 of byte0 of each column."""
    return np.packbits(swath, axis=1, bitorder="little").tobytes()


def frames_for_image(img, hdpi=300, vdpi=300, head=HP45):
    bm = page_bitmap(img, hdpi, vdpi)
    feed_um = round(swath_feed_mm(head, vdpi) * 1000)
    bpc = (head.nozzles + 7) // 8
    for i, sw in enumerate(slice_page(bm, head, vdpi)):
        direction = 1 if i % 2 == 0 else -1
        yield from swath_frames(i, pack_columns(sw), sw.shape[0], bpc, direction, feed_um)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?")
    ap.add_argument("--dpi", type=int, default=300)
    a = ap.parse_args(argv)
    img = Image.open(a.image or sys.stdin.buffer)
    for f in frames_for_image(img, a.dpi, a.dpi):
        sys.stdout.buffer.write(f)


if __name__ == "__main__":
    main()
