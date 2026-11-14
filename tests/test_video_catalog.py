"""Filesystem listing contract; no GTK, NumPy, codec, or real video needed."""
import tempfile
import unittest
from pathlib import Path

from x8cv.video_catalog import list_videos


class VideoCatalogTests(unittest.TestCase):
    def test_lists_only_playable_basenames_in_name_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("z.x8cv", "a clip.x8cv", "영상.x8cv", "font.npz", "upper.X8CV"):
                (root / name).write_bytes(b"")
            (root / "folder.x8cv").mkdir()
            (root / "folder.x8cv" / "nested.x8cv").write_bytes(b"")
            self.assertEqual(list_videos(root), ["a clip.x8cv", "z.x8cv", "영상.x8cv"])

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(list_videos(directory), [])

    def test_missing_directory_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                list_videos(Path(directory) / "missing")

    def test_new_files_are_visible_on_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(list_videos(directory), [])
            path = Path(directory) / "new.x8cv"
            path.write_bytes(b"")
            self.assertEqual(list_videos(directory), ["new.x8cv"])
            path.unlink()
            self.assertEqual(list_videos(directory), [])


if __name__ == "__main__":
    unittest.main()
