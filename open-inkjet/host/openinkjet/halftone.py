import numpy as np
from PIL import Image


def floyd_steinberg(gray: np.ndarray) -> np.ndarray:
    """gray: 0(black)..255(white) array. Returns uint8 array, 1 = ink. Uses PIL's C implementation."""
    im = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), "L").convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    return (np.asarray(im) == 0).astype(np.uint8)
