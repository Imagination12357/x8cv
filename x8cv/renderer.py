"""X8CV -> indexed decoded cells -> Unicode text, without GTK dependencies.

FrameSource loads the NPZ once at construction. NumPy and libzstd are required;
render_frame(raw, chars, masks, width, height) receives cell dimensions and a
loaded glyph table explicitly.
"""
from pathlib import Path

import numpy as np

from x8cv.format import (
    CELL_BYTES, HEADER, CHUNK_LENGTH, OFFSET, read_header, validate_dimensions,
)
from x8cv.zstd_codec import decompress
from x8cv.glyphs import get_glyphs

# NumPy 1.x lacks np.bitwise_count; use a byte lookup table when unavailable.
_POPCOUNT_LUT = np.unpackbits(
    np.arange(256, dtype=np.uint8)[:, None], axis=1
).sum(axis=1).astype(np.uint8)


def hamming_distances(cells, masks):
    xor = cells[:, None] ^ masks[None, :]
    if hasattr(np, "bitwise_count"):
        return np.bitwise_count(xor)
    # Equivalent vectorized byte-table popcount on NumPy < 2.0.
    return _POPCOUNT_LUT[xor.view(np.uint8).reshape(len(cells), len(masks), 8)].sum(
        axis=2, dtype=np.uint8
    )


def render_frame(raw: bytes, chars, masks, width, height) -> str:
    validate_dimensions(width, height)
    cells = np.frombuffer(raw, dtype="<u8")
    if cells.size != width * height:
        raise ValueError("Incomplete frame")

    # Compare every cell against the loaded, deduplicated glyph table.
    distance = hamming_distances(cells, masks)
    best = distance.argmin(axis=1).reshape(height, width)

    # Reinterpret each contiguous U1 row as one runtime-width Unicode string.
    matched = np.ascontiguousarray(chars[best])
    return "\n".join(matched.view(f"U{width}").reshape(height))


class FrameSource:
    def __init__(self, path, glyph_path=None):
        self.chars, self.masks = get_glyphs(glyph_path)
        self.file = Path(path).open("rb")
        try:
            (self.width, self.height, self.fps_num, self.fps_den,
             self.frame_count, index_offset) = read_header(self.file)
            self.frame_bytes = self.width * self.height * CELL_BYTES
            self.file.seek(0, 2)
            size = self.file.tell()
            if index_offset + self.frame_count * OFFSET.size != size:
                raise ValueError("Invalid X8CV offset table")
            self.file.seek(index_offset)
            self.offsets = np.frombuffer(self.file.read(self.frame_count * OFFSET.size), dtype="<u8").copy()
            if np.any(self.offsets < HEADER.size) or np.any(self.offsets >= index_offset):
                raise ValueError("Invalid X8CV frame offset")
            self.index_offset = index_offset
        except Exception:
            self.file.close()
            raise

    @property
    def fps(self):
        return self.fps_num / self.fps_den

    def get_frame(self, index: int) -> str:
        if index < 0 or index >= self.frame_count:
            raise IndexError(index)
        offset = int(self.offsets[index])
        limit = int(self.offsets[index + 1]) if index + 1 < self.frame_count else self.index_offset
        self.file.seek(offset)
        length_raw = self.file.read(CHUNK_LENGTH.size)
        if len(length_raw) != CHUNK_LENGTH.size:
            raise ValueError("Truncated frame")
        length = CHUNK_LENGTH.unpack(length_raw)[0]
        if length != limit - offset - CHUNK_LENGTH.size:
            raise ValueError("Invalid compressed frame length")
        payload = self.file.read(length)
        if len(payload) != length:
            raise ValueError("Truncated compressed frame")
        return render_frame(decompress(payload, self.frame_bytes), self.chars,
                            self.masks, self.width, self.height)

    def close(self):
        self.file.close()
