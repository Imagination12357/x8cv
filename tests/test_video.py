"""Variable X8CV rendering and indexed seeking with a synthetic glyph table."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from x8cv.format import MAGIC, VERSION, HEADER, CELL_BYTES, CHUNK_LENGTH, OFFSET
from x8cv.preprocess import encode_frame
from x8cv.renderer import FrameSource, render_frame, hamming_distances
from x8cv.zstd_codec import compress, decompress


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.chars = np.array([" ", "█", chr(0x1FB00)], dtype="U1")
        self.masks = np.array([0, 0xFFFFFFFFFFFFFFFF, 1], dtype="<u8")

    def write_video(self, path, width, height):
        frame_bytes = width * height * CELL_BYTES
        frames = [bytes(frame_bytes), bytes([255]) * frame_bytes]
        with path.open("wb") as target:
            target.write(HEADER.pack(MAGIC, VERSION, width, height, 30, 1, 0, 0))
            offsets = []
            for frame in frames:
                offsets.append(target.tell())
                payload = compress(frame)
                target.write(CHUNK_LENGTH.pack(len(payload)) + payload)
            index_offset = target.tell()
            for offset in offsets:
                target.write(OFFSET.pack(offset))
            target.seek(0)
            target.write(HEADER.pack(MAGIC, VERSION, width, height,
                                     30, 1, len(frames), index_offset))

    def test_white_1080p_source_keeps_original_output(self):
        encoded = encode_frame(bytes([255]) * (1920 * 1080), 1920, 1080, 3)
        self.assertEqual(len(encoded), 80 * 45 * CELL_BYTES)
        self.assertEqual(render_frame(encoded, self.chars, self.masks, 80, 45),
                         "\n".join([" " * 80] * 45))

    def test_runtime_row_width_preserves_supplementary_characters(self):
        for width, height in ((1, 1), (3, 2), (160, 60)):
            with self.subTest(width=width, height=height):
                cells = np.ones(width * height, dtype="<u8").tobytes()
                rows = render_frame(cells, self.chars, self.masks, width, height).split("\n")
                self.assertEqual(rows, [chr(0x1FB00) * width] * height)

    def test_cell_order_is_preserved_across_rows(self):
        cells = np.array([0, 1, 0xFFFFFFFFFFFFFFFF, 1, 0, 0], dtype="<u8")
        self.assertEqual(render_frame(cells.tobytes(), self.chars, self.masks, 3, 2),
                         " " + chr(0x1FB00) + "█\n" + chr(0x1FB00) + "  ")

    def test_wrong_decoded_size_is_rejected(self):
        with self.assertRaises(ValueError):
            render_frame(bytes(5 * CELL_BYTES), self.chars, self.masks, 3, 2)

    def test_hamming_counts_all_64_bits(self):
        cells = np.array([0, 1, 0xFFFFFFFFFFFFFFFF], dtype="<u8")
        np.testing.assert_array_equal(
            hamming_distances(cells, self.masks),
            [[0, 64, 1], [1, 63, 0], [64, 0, 63]],
        )

    def test_tied_matches_keep_first_glyph(self):
        chars = np.array(["a", "b"], dtype="U1")
        masks = np.array([1, 2], dtype="<u8")
        self.assertEqual(render_frame(bytes(6 * CELL_BYTES), chars, masks, 3, 2), "aaa\naaa")

    def test_zstd_round_trip(self):
        original = b"123" * 1000
        self.assertEqual(decompress(compress(original), len(original)), original)

    def test_index_seek_uses_header_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.x8cv"
            glyph_path = Path(directory) / "glyphs.npz"
            np.savez(glyph_path, chars=self.chars, masks=self.masks)
            for width, height in ((1, 1), (3, 2), (80, 45), (160, 60)):
                with self.subTest(width=width, height=height):
                    self.write_video(path, width, height)
                    source = FrameSource(path, glyph_path)
                    try:
                        self.assertEqual((source.width, source.height), (width, height))
                        self.assertEqual(source.frame_bytes, width * height * CELL_BYTES)
                        self.assertEqual(source.fps, 30)
                        self.assertEqual(source.frame_count, 2)
                        self.assertEqual(source.get_frame(1), "\n".join(["█" * width] * height))
                        self.assertEqual(source.get_frame(0), "\n".join([" " * width] * height))
                        self.assertEqual(source.get_frame(1), "\n".join(["█" * width] * height))
                        for index in (-1, 2):
                            with self.assertRaises(IndexError):
                                source.get_frame(index)
                    finally:
                        source.close()

    def test_glyph_loading_is_deferred_until_source_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "build-glyphs"):
                FrameSource(Path(directory) / "video.x8cv", Path(directory) / "missing.npz")


if __name__ == "__main__":
    unittest.main()
