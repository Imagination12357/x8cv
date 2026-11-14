"""Load HEX-extracted NPZ into contiguous U1 characters and little-endian u64 masks.

Input: an NPZ path, defaulting to data/glyphs_unscii.npz. Used by FrameSource;
requires NumPy. There is no fallback when the table is absent or invalid.
"""
from pathlib import Path

import numpy as np

DEFAULT_GLYPH_PATH = Path(__file__).resolve().parent.parent / "data" / "glyphs_unscii.npz"


def get_glyphs(path=None):
    path = Path(path) if path is not None else DEFAULT_GLYPH_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"Glyph table not found: {path}. Build it from the project root with: "
            f'python3 -m x8cv build-glyphs /path/to/unscii-8.hex "{path}"'
        )
    with np.load(path, allow_pickle=False) as data:
        if "chars" not in data or "masks" not in data:
            raise ValueError(f"Glyph table must contain chars and masks: {path}")
        chars, masks = data["chars"].copy(), data["masks"].copy()
    if (chars.ndim != 1 or masks.ndim != 1 or not chars.size
            or chars.size != masks.size
            or chars.dtype != np.dtype("U1") or masks.dtype != np.dtype("<u8")):
        raise ValueError(f"Expected matching nonempty U1/u64 glyph arrays: {path}")
    if (len(set(chars.tolist())) != chars.size
            or len(set(map(int, masks))) != masks.size
            or np.any(chars == "")):
        raise ValueError(f"Glyph characters and masks must be nonempty and unique: {path}")
    return chars, masks
