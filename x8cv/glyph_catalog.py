"""Ordered Unscii-8 extraction candidates; no bitmap generation or runtime I/O.

Consumed by build_glyphs. Earlier characters win when HEX masks are identical.
"""

BASE_CODEPOINTS = (
    (0x0020,)
    + tuple(range(0x2580, 0x2591))
    + tuple(range(0x2594, 0x25A0))
)
EXCLUDED_CODEPOINTS = {0x1FB7C, 0x1FB7D, 0x1FB7E, 0x1FB7F, 0x1FB81}

CODEPOINTS = (
    BASE_CODEPOINTS
    + tuple(cp for cp in range(0x1FB00, 0x1FB8C)
            if cp not in EXCLUDED_CODEPOINTS)
    + tuple(range(0x2800, 0x2900))
    + tuple(range(0x25E2, 0x25E6))
    + (0x1FB9A, 0x1FB9B)
)
