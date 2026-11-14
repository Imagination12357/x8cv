"""Downscale decisions, majority reduction, and a synthetic preprocessing stream."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from x8cv.format import read_header
from x8cv.preprocess import (
    select_downscale, encode_frame, read_frame, preprocess,
)
from x8cv.renderer import FrameSource


class PreprocessTests(unittest.TestCase):
    def test_default_target_selects_original_1080p_scale(self):
        self.assertEqual(select_downscale(1920, 1080), (3, 80, 45))

    def test_other_sources_and_targets(self):
        for args, expected in (
            ((1280, 720), (2, 80, 45)),
            ((8, 8), (1, 1, 1)),
            ((800, 800, None, 10000), (1, 100, 100)),
            ((1920, 1080, None, 1296), (5, 48, 27)),
            ((1920, 1080, None, 144), (15, 16, 9)),
            ((1920, 1080, None, 0), (15, 16, 9)),
        ):
            with self.subTest(args=args):
                self.assertEqual(select_downscale(*args), expected)

    def test_target_tie_prefers_larger_glyph_count(self):
        self.assertEqual(select_downscale(32, 32, target_glyphs=10), (1, 4, 4))

    def test_no_valid_candidate(self):
        with self.assertRaisesRegex(ValueError, "10000"):
            select_downscale(80008, 8)

    def test_invalid_source_dimensions(self):
        for width, height in ((0, 8), (-8, 8), (8, 0), (9, 8), (8, 9), (8.0, 8)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    select_downscale(width, height)

    def test_manual_scale_ignores_target(self):
        for target in (1, 3600, 99999, -1):
            self.assertEqual(select_downscale(1920, 1080, 5, target), (5, 48, 27))

    def test_manual_scale_must_be_positive_integral_and_divide_both_axes(self):
        for scale in (0, -1, 1.5, 2, 16):
            with self.subTest(scale=scale):
                with self.assertRaises(ValueError):
                    select_downscale(1920, 1080, scale)

    def test_manual_scale_obeys_glyph_limit(self):
        self.assertEqual(select_downscale(800, 800, 1), (1, 100, 100))
        with self.assertRaises(ValueError):
            select_downscale(1920, 1080, 1)

    def test_scale_one_preserves_bit_order_and_threshold(self):
        image = np.full((8, 8), 255, dtype=np.uint8)
        image[0, 0] = 0
        image[0, 1] = 128
        image[-1, -1] = 127
        self.assertEqual(int.from_bytes(encode_frame(image.tobytes(), 8, 8, 1), "little"),
                         1 | (1 << 63))

    def test_even_scale_tie_is_light_and_majority_is_dark(self):
        image = np.full((16, 16), 255, dtype=np.uint8)
        image[0, :2] = 0
        self.assertEqual(encode_frame(image.tobytes(), 16, 16, 2), bytes(8))
        image[1, 0] = 0
        self.assertEqual(int.from_bytes(encode_frame(image.tobytes(), 16, 16, 2), "little"), 1)

    def test_odd_scale_requires_five_of_nine_dark_pixels(self):
        image = np.full((24, 24), 255, dtype=np.uint8)
        image[:2, :2] = 0
        self.assertEqual(encode_frame(image.tobytes(), 24, 24, 3), bytes(8))
        image[0, 2] = 0
        self.assertEqual(int.from_bytes(encode_frame(image.tobytes(), 24, 24, 3), "little"), 1)

    def test_non_square_encoding_keeps_cells_in_row_order(self):
        image = np.full((16, 32), 255, dtype=np.uint8)
        image[:, :16] = 0
        self.assertEqual(encode_frame(image.tobytes(), 32, 16, 2),
                         bytes([255]) * 8 + bytes(8))

    def test_incomplete_source_frame_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_frame(bytes(63), 8, 8, 1)

    def test_frame_reader_uses_requested_source_size(self):
        stream = io.BytesIO(b"abcdefgh")
        self.assertEqual(read_frame(stream, 4), b"abcd")
        self.assertEqual(read_frame(stream, 4), b"efgh")
        self.assertIsNone(read_frame(stream, 4))
        with self.assertRaises(ValueError):
            read_frame(io.BytesIO(b"abc"), 4)

    def test_preprocessing_writes_selected_dimensions_and_decodable_payload(self):
        # Replace external video I/O, but exercise the real encoding/format/codec path.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.x8cv"
            glyph_path = Path(directory) / "glyphs.npz"
            np.savez(glyph_path, chars=np.array([" "], dtype="U1"),
                     masks=np.array([0], dtype="<u8"))
            for scale, target, width, height in ((None, 2, 2, 1),
                                                 (2, 99999, 2, 1),
                                                 (None, 3600, 4, 2)):
                with self.subTest(scale=scale, target=target):
                    events = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    process = SimpleNamespace(stdout=io.BytesIO(bytes([255]) * (32 * 16)),
                                              wait=lambda: 0, poll=lambda: 0)
                    with patch("x8cv.preprocess.probe_video", return_value=(32, 16, None)), \
                            patch("x8cv.preprocess.subprocess.Popen", return_value=process), \
                            contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        result = preprocess("input.mp4", path, downscale=scale,
                                            target_glyphs=target,
                                            progress=lambda stage, info: events.append((stage, info)))
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertEqual(stderr.getvalue(), "")
                    self.assertEqual(result["frame_count"], 1)
                    self.assertEqual(result["fps"], 30)
                    self.assertEqual(result["raw_bytes"], width * height * 8)
                    self.assertEqual(result["output_bytes"], path.stat().st_size)
                    self.assertEqual(result["output_path"], path)
                    self.assertGreaterEqual(result["elapsed"], 0)
                    stages = [stage for stage, _ in events]
                    self.assertEqual(stages[:2], ["probe", "processing"])
                    self.assertEqual(stages[-1], "index")
                    self.assertEqual(events[1][1]["width"], width)
                    self.assertEqual(events[1][1]["height"], height)
                    updates = [info for stage, info in events if stage == "progress"]
                    self.assertTrue(updates[-1]["final"])
                    with path.open("rb") as source:
                        self.assertEqual(read_header(source)[:5], (width, height, 30, 1, 1))
                    source = FrameSource(path, glyph_path)
                    try:
                        self.assertEqual(source.get_frame(0), "\n".join([" " * width] * height))
                    finally:
                        source.close()

    def test_no_callback_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silent.x8cv"
            process = SimpleNamespace(stdout=io.BytesIO(bytes([255]) * 64),
                                      wait=lambda: 0, poll=lambda: 0)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("x8cv.preprocess.probe_video", return_value=(8, 8, None)), \
                    patch("x8cv.preprocess.subprocess.Popen", return_value=process), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = preprocess("input.mp4", path)
            self.assertEqual(result["frame_count"], 1)
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_callback_failure_removes_partial_output_and_closes_decoder(self):
        def report(stage, details):
            if stage == "progress":
                raise RuntimeError("callback failed")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.x8cv"
            stream = io.BytesIO(bytes([255]) * 64)
            process = SimpleNamespace(stdout=stream, wait=Mock(return_value=0),
                                      poll=Mock(return_value=None), kill=Mock())
            with patch("x8cv.preprocess.probe_video", return_value=(8, 8, None)), \
                    patch("x8cv.preprocess.subprocess.Popen", return_value=process), \
                    patch("x8cv.preprocess.PROGRESS_INTERVAL", 0):
                with self.assertRaisesRegex(RuntimeError, "callback failed"):
                    preprocess("input.mp4", path, progress=report)
            self.assertFalse(path.exists())
            self.assertTrue(stream.closed)
            process.kill.assert_called_once_with()
            self.assertTrue(process.wait.called)


if __name__ == "__main__":
    unittest.main()
