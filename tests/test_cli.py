"""Unified CLI dispatch, output, and lazy dependency loading; no real FFmpeg."""
import builtins
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from x8cv import cli
from x8cv.format import read_header
from x8cv.glyph_catalog import CODEPOINTS


class CliTests(unittest.TestCase):
    def test_preprocess_arguments(self):
        args = cli.parse_args(["preprocess", "input.mp4", "output.x8cv", "24",
                               "--downscale", "2", "--target-glyphs", "100"])
        self.assertEqual(args.command, "preprocess")
        self.assertEqual((args.fps, args.downscale, args.target_glyphs), ("24", 2, 100))
        defaults = cli.parse_args(["preprocess", "input.mp4", "output.x8cv"])
        self.assertEqual((defaults.fps, defaults.downscale, defaults.target_glyphs),
                         ("30", None, None))

    def test_glyph_builder_arguments(self):
        args = cli.parse_args(["build-glyphs", "font.hex", "glyphs.npz"])
        self.assertEqual((args.command, args.hex_path, args.output_path),
                         ("build-glyphs", "font.hex", "glyphs.npz"))
        self.assertIsNone(cli.parse_args(["build-glyphs", "font.hex"]).output_path)

    def test_help_does_not_import_processing_dependencies(self):
        original_import = builtins.__import__

        def lightweight_import(name, *args, **kwargs):
            if (name == "numpy" or name.startswith("numpy.")
                    or name in ("preprocess", "build_glyphs", "x8cv.preprocess", "x8cv.build_glyphs")):
                raise AssertionError(f"Help imported processing dependency: {name}")
            return original_import(name, *args, **kwargs)

        for arguments in (["--help"], ["preprocess", "--help"], ["build-glyphs", "--help"]):
            with self.subTest(arguments=arguments), \
                    patch("builtins.__import__", side_effect=lightweight_import), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as exit_status:
                    cli.main(arguments)
                self.assertEqual(exit_status.exception.code, 0)
                self.assertIn("usage:", output.getvalue())

    def test_missing_subcommand_is_an_argument_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_status:
                cli.main([])
        self.assertEqual(exit_status.exception.code, 2)

    def test_preprocess_command_writes_video_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.x8cv"
            process = SimpleNamespace(stdout=io.BytesIO(bytes([255]) * 64),
                                      wait=lambda: 0, poll=lambda: 0)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("x8cv.preprocess.probe_video", return_value=(8, 8, None)), \
                    patch("x8cv.preprocess.subprocess.Popen", return_value=process), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = cli.main(["preprocess", "input.mp4", str(path), "24"])
            self.assertEqual(status, 0)
            with path.open("rb") as source:
                self.assertEqual(read_header(source)[:5], (1, 1, 24, 1, 1))
            self.assertIn("Downscale   : 1", stdout.getvalue())
            self.assertIn("1x1 cells", stdout.getvalue())
            self.assertIn("Completed!", stdout.getvalue())
            self.assertIn("1 frames", stderr.getvalue())

    def test_builder_command_does_not_import_codec(self):
        original_import = builtins.__import__

        def without_codec(name, *args, **kwargs):
            if name in ("x8cv.zstd_codec", "zstd_codec", "x8cv.preprocess", "preprocess"):
                raise AssertionError(f"Builder imported unrelated processing dependency: {name}")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "font.hex"
            output = Path(directory) / "glyphs.npz"
            source.write_text("\n".join(f"{cp:05X}:{index + 1:016X}"
                                        for index, cp in enumerate(CODEPOINTS)), encoding="ascii")
            with patch("builtins.__import__", side_effect=without_codec), \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = cli.main(["build-glyphs", str(source), str(output)])
            self.assertEqual(status, 0)
            self.assertTrue(output.is_file())
            self.assertIn("Saved 427 unique glyphs from 427 codepoints", stdout.getvalue())

    def test_operational_error_returns_one_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.hex"
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = cli.main(["build-glyphs", str(missing)])
            self.assertEqual(status, 1)
            self.assertIn("x8cv: error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_manual_scale_rejection_is_reported_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.x8cv"
            with patch("x8cv.preprocess.probe_video", return_value=(1920, 1080, None)), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = cli.main(["preprocess", "input.mp4", str(path), "--downscale", "2"])
            self.assertEqual(status, 1)
            self.assertFalse(path.exists())
            self.assertIn("Downscale", stderr.getvalue())

    def test_interrupt_returns_130(self):
        with patch("x8cv.build_glyphs.build", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = cli.main(["build-glyphs", "font.hex"])
        self.assertEqual(status, 130)
        self.assertIn("x8cv: cancelled", stderr.getvalue())

    def test_invalid_fps_is_reported_before_probing(self):
        for fps in ("1/0", "invalid"):
            with self.subTest(fps=fps), \
                    patch("x8cv.preprocess.probe_video") as probe, \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = cli.main(["preprocess", "input.mp4", "output.x8cv", fps])
            self.assertEqual(status, 1)
            self.assertIn("x8cv: error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
