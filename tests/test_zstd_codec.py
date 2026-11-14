"""Codec contracts for real standard-library and ctypes backends on Linux."""
import builtins
import importlib.util
import unittest
from unittest.mock import patch

from x8cv import zstd_codec


def load_codec(force_ctypes=False):
    original_import = builtins.__import__

    def import_backend(name, *args, **kwargs):
        if force_ctypes and name == "compression":
            raise ImportError("Standard backend deliberately unavailable for this test")
        return original_import(name, *args, **kwargs)

    spec = importlib.util.spec_from_file_location("codec_test_instance", zstd_codec.__file__)
    module = importlib.util.module_from_spec(spec)
    with patch("builtins.__import__", side_effect=import_backend):
        spec.loader.exec_module(module)
    return module


class CodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctypes_codec = load_codec(force_ctypes=True)
        cls.default_codec = load_codec()
        cls.codecs = (cls.ctypes_codec, cls.default_codec)

    def test_backend_interoperability(self):
        for raw in (b"", b"\x00\xff" * 100, b"abc" * 1000):
            for encoder in self.codecs:
                for decoder in self.codecs:
                    with self.subTest(raw_size=len(raw), encoder=encoder, decoder=decoder):
                        self.assertEqual(decoder.decompress(encoder.compress(raw), len(raw)), raw)

    def test_concatenated_frames(self):
        for encoder in self.codecs:
            payload = encoder.compress(b"abc") + encoder.compress(b"def")
            for decoder in self.codecs:
                self.assertEqual(decoder.decompress(payload, 6), b"abcdef")

    def test_smaller_decoded_output_is_value_error(self):
        for codec in self.codecs:
            with self.assertRaises(ValueError):
                codec.decompress(codec.compress(b"abc"), 4)

    def test_larger_decoded_output_is_runtime_error(self):
        for codec in self.codecs:
            with self.assertRaises(RuntimeError):
                codec.decompress(codec.compress(b"x" * 10000), 3)

    def test_corrupt_and_truncated_payloads_are_runtime_errors(self):
        for codec in self.codecs:
            payload = codec.compress(b"abcdef" * 100)
            for invalid in (b"", b"not a zstd frame", payload[:-1], payload + b"garbage"):
                with self.subTest(codec=codec, payload=invalid):
                    with self.assertRaises(RuntimeError):
                        codec.decompress(invalid, 600)

    def test_empty_input_is_not_an_encoded_empty_frame(self):
        for codec in self.codecs:
            with self.assertRaises(RuntimeError):
                codec.decompress(b"", 0)

    def test_invalid_expected_size_is_value_error(self):
        for codec in self.codecs:
            for expected_size in (-1, 1.5):
                with self.assertRaises(ValueError):
                    codec.decompress(b"", expected_size)

    def test_available_standard_backend_does_not_load_system_library(self):
        if self.default_codec._zstd is None:
            self.skipTest("compression.zstd is unavailable in this Python build")
        with patch("ctypes.CDLL", side_effect=AssertionError("Unexpected ctypes backend")):
            codec = load_codec()
            self.assertEqual(codec.decompress(codec.compress(b"hello"), 5), b"hello")

    def test_standard_codec_error_does_not_switch_backends(self):
        codec = self.default_codec
        if codec._zstd is None:
            self.skipTest("compression.zstd is unavailable in this Python build")
        with patch("ctypes.CDLL", side_effect=AssertionError("Unexpected fallback")):
            with self.assertRaises(RuntimeError):
                codec.decompress(b"invalid", 8)


if __name__ == "__main__":
    unittest.main()
