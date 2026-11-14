"""X8CV v1: versioned header, independently zstd-compressed frames, u64 index.

Shared by preprocess and renderer. read_header(file) returns cell width/height,
FPS numerator/denominator, frame count, and index offset. Standard library only.
"""
import struct
MAGIC = b"X8CV"
VERSION = 1
CELL_SIZE = 8
CELL_BYTES = 8
MAX_GLYPHS = 10000
HEADER = struct.Struct("<4sHHHIIQQ")
CHUNK_LENGTH = struct.Struct("<I")
OFFSET = struct.Struct("<Q")


def validate_dimensions(width, height):
    if (not isinstance(width, int) or not isinstance(height, int)
            or width <= 0 or height <= 0 or width * height > MAX_GLYPHS):
        raise ValueError(f"Expected positive cell dimensions with at most {MAX_GLYPHS} glyphs")


def read_header(file):
    raw = file.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError("Truncated X8CV header")
    magic, version, width, height, num, den, count, index_offset = HEADER.unpack(raw)
    if magic != MAGIC:
        raise ValueError("Not an X8CV video")
    if version != VERSION:
        raise ValueError(f"Unsupported X8CV version: {version}")
    validate_dimensions(width, height)
    if not num or not den or not count or index_offset < HEADER.size:
        raise ValueError("Invalid X8CV header")
    return width, height, num, den, count, index_offset
