"""Extract exact 8x8 tiles from upstream Unscii-8 .hex, deduplicate and save NPZ.
Input: Unscii-8 HEX and the ordered glyph_catalog.CODEPOINTS.
Output: data/glyphs_unscii.npz by default. Requires NumPy, not GTK or libzstd.
Returns the unique glyph count; validation errors include missing/wrong-size
code points. The command-line entry point is python3 -m x8cv build-glyphs.
"""
from pathlib import Path
import numpy as np

from x8cv.glyph_catalog import CODEPOINTS

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "glyphs_unscii.npz"


def build(hex_path, output=None):
    table = {}
    for raw in Path(hex_path).read_text(encoding="ascii").splitlines():
        if ":" not in raw:
            continue
        code, bitmap = raw.strip().split(":", 1)
        try:
            table[int(code, 16)] = bytes.fromhex(bitmap)
        except ValueError:
            continue

    chars, masks, seen, missing, non8 = [], [], set(), [], []
    for cp in CODEPOINTS:
        bitmap = table.get(cp)
        if bitmap is None:
            missing.append(cp)
            continue
        if len(bitmap) != 8:
            non8.append(cp)
            continue
        # Unscii .hex is 8 consecutive rows, most significant bit at left.
        rows = np.unpackbits(np.frombuffer(bitmap, dtype=np.uint8), bitorder="big")
        mask = int.from_bytes(np.packbits(rows, bitorder="little").tobytes(), "little")
        if mask in seen:
            continue
        seen.add(mask)
        chars.append(chr(cp))
        masks.append(mask)
    if missing or non8:
        details = []
        if missing:
            details.append("Missing: " + " ".join(f"U+{x:04X}" for x in missing))
        if non8:
            details.append("Not 8x8: " + " ".join(f"U+{x:04X}" for x in non8))
        raise ValueError("Font lacks required 8x8 glyphs; check correct Unscii-8 HEX version\n"
                         + "\n".join(details))
    output = Path(output) if output is not None else DEFAULT_OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output, chars=np.array(chars, dtype="U1"), masks=np.array(masks, dtype="<u8"))
    return len(chars)
