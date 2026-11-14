"""HEX extraction and NPZ contracts; uses synthetic font data, not a bundled font."""
import tempfile
import unittest
import contextlib
import io
from pathlib import Path

import numpy as np

from x8cv.build_glyphs import build
from x8cv.glyph_catalog import CODEPOINTS
from x8cv.glyphs import get_glyphs


class GlyphTests(unittest.TestCase):
    def write_hex(self, directory, replacements=None, omitted=()):
        replacements = replacements or {}
        lines = []
        for index, cp in enumerate(CODEPOINTS):
            if cp not in omitted:
                bitmap = replacements.get(cp, f"{index + 1:016X}")
                lines.append(f"{cp:05X}:{bitmap}")
        path = Path(directory) / "font.hex"
        path.write_text("\n".join(lines), encoding="ascii")
        return path

    def test_catalog_contains_approved_candidates(self):
        codes = set(CODEPOINTS)
        self.assertEqual(len(CODEPOINTS), 427)
        self.assertEqual(len(codes), 427)
        self.assertEqual(CODEPOINTS[0], 0x0020)
        self.assertEqual(set(CODEPOINTS[:30]),
                         {0x0020} | set(range(0x2580, 0x2591)) | set(range(0x2594, 0x25A0)))
        self.assertTrue(codes.isdisjoint({0x2591, 0x2592, 0x2593}))
        for start, stop in ((0x1FB00, 0x1FB3C), (0x2800, 0x2900),
                            (0x25E2, 0x25E6), (0x1FB9A, 0x1FB9C)):
            self.assertTrue(set(range(start, stop)).issubset(codes))
        self.assertTrue(codes.isdisjoint({0x1FB7C, 0x1FB7D, 0x1FB7E,
                                          0x1FB7F, 0x1FB81}))

    def test_hex_row_bits_become_little_endian_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_hex(directory, {
                CODEPOINTS[0]: "0000000000000000",
                CODEPOINTS[1]: "8000000000000000",
                CODEPOINTS[2]: "0000000000000001",
            })
            output = Path(directory) / "glyphs.npz"
            build(source, output)
            chars, masks = get_glyphs(output)
            self.assertEqual(list(chars[:3]), [chr(cp) for cp in CODEPOINTS[:3]])
            self.assertEqual([int(mask) for mask in masks[:3]], [0, 1, 1 << 63])

    def test_duplicate_masks_keep_first_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_hex(directory, {
                CODEPOINTS[0]: "0000000000000000",
                CODEPOINTS[1]: "0000000000000000",
            })
            output = Path(directory) / "glyphs.npz"
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(build(source, output), 426)
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))
            chars, masks = get_glyphs(output)
            self.assertEqual(chars[0], chr(CODEPOINTS[0]))
            self.assertNotIn(chr(CODEPOINTS[1]), chars)
            self.assertEqual(len(set(map(int, masks))), 426)

    def test_invalid_font_does_not_overwrite_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "glyphs.npz"
            output.write_bytes(b"existing output")
            for replacements, omitted in (({}, (CODEPOINTS[0],)),
                                            ({CODEPOINTS[0]: "FF" * 16}, ())):
                with self.subTest(replacements=replacements, omitted=omitted):
                    source = self.write_hex(directory, replacements, omitted)
                    with self.assertRaises(ValueError) as error:
                        build(source, output)
                    self.assertIn(f"U+{CODEPOINTS[0]:04X}", str(error.exception))
                    self.assertEqual(output.read_bytes(), b"existing output")

    def test_missing_npz_explains_build_command(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError,
                                        "python3 -m x8cv build-glyphs"):
                get_glyphs(Path(directory) / "missing.npz")

    def test_invalid_npz_tables_are_rejected(self):
        cases = [
            {"chars": np.array([" "], dtype="U1")},
            {"chars": np.array([], dtype="U1"), "masks": np.array([], dtype="<u8")},
            {"chars": np.array([" ", "█"], dtype="U1"),
             "masks": np.array([0], dtype="<u8")},
            {"chars": np.array([[" "]], dtype="U1"),
             "masks": np.array([0], dtype="<u8")},
            {"chars": np.array(["ab"], dtype="U2"),
             "masks": np.array([0], dtype="<u8")},
            {"chars": np.array([" "], dtype="U1"),
             "masks": np.array([0], dtype="<u4")},
            {"chars": np.array([" ", "█"], dtype="U1"),
             "masks": np.array([0, 0], dtype="<u8")},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "glyphs.npz"
            for index, arrays in enumerate(cases):
                with self.subTest(case=index):
                    np.savez(path, **arrays)
                    with self.assertRaises(ValueError):
                        get_glyphs(path)


if __name__ == "__main__":
    unittest.main()
