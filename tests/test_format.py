"""X8CV header layout and variable cell dimensions; no external dependencies."""
import io
import unittest

from x8cv.format import MAGIC, VERSION, HEADER, read_header


class FormatTests(unittest.TestCase):
    def header(self, **changes):
        values = dict(magic=MAGIC, version=VERSION, width=80, height=45,
                      num=30, den=1, count=2, index_offset=100)
        values.update(changes)
        return HEADER.pack(*values.values())

    def test_header_layout_and_values(self):
        raw = self.header()
        self.assertEqual(HEADER.size, 34)
        self.assertEqual(raw[:10], b"X8CV\x01\x00\x50\x00\x2d\x00")
        self.assertEqual(read_header(io.BytesIO(raw)), (80, 45, 30, 1, 2, 100))

    def test_variable_dimensions_are_returned(self):
        for width, height in ((1, 1), (160, 60), (10000, 1), (1, 10000), (100, 100)):
            with self.subTest(width=width, height=height):
                self.assertEqual(read_header(io.BytesIO(self.header(width=width, height=height))),
                                 (width, height, 30, 1, 2, 100))

    def test_old_magic_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "X8CV"):
            read_header(io.BytesIO(self.header(magic=b"XBA2")))

    def test_unknown_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version"):
            read_header(io.BytesIO(self.header(version=2)))

    def test_invalid_header_fields_are_rejected(self):
        for changes in ({"width": 0}, {"height": 0}, {"width": 101, "height": 100},
                        {"num": 0}, {"den": 0}, {"count": 0},
                        {"index_offset": HEADER.size - 1}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    read_header(io.BytesIO(self.header(**changes)))

    def test_truncated_header_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            read_header(io.BytesIO(self.header()[:-1]))


if __name__ == "__main__":
    unittest.main()
