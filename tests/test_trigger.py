"""Filename command parsing without GTK, filesystem access, or generated data."""
import unittest

from x8cv.trigger import LIST_TRIGGER, parse_trigger


class TriggerTests(unittest.TestCase):
    def test_list_command_is_distinct_from_filename(self):
        self.assertEqual(LIST_TRIGGER, ":videos\n")
        self.assertIsNone(parse_trigger(LIST_TRIGGER))

    def test_filename_requires_enter(self):
        self.assertIsNone(parse_trigger("badapple.x8cv"))
        self.assertEqual(parse_trigger("badapple.x8cv\n"), "badapple.x8cv")

    def test_preserves_exact_filename(self):
        for name in ("Bad Apple!!.x8cv", "영상.x8cv", "clip.v2.x8cv", " clip.x8cv"):
            with self.subTest(name=name):
                self.assertEqual(parse_trigger(name + "\n"), name)

    def test_ignores_non_video_commands(self):
        for text in ("", "\n", "Bad Apple!!\n", "clip.mp4\n", "clip.x8cv \n"):
            with self.subTest(text=text):
                self.assertIsNone(parse_trigger(text))

    def test_rejects_extra_lines_and_carriage_returns(self):
        for text in ("clip.x8cv\n\n", "intro\nclip.x8cv\n",
                     "clip.x8cv\nother.x8cv\n", "clip.x8cv\r\n"):
            with self.subTest(text=text):
                self.assertIsNone(parse_trigger(text))

    def test_rejects_paths_and_nul(self):
        for name in ("../clip.x8cv", "data/clip.x8cv", "/tmp/clip.x8cv",
                     "..\\clip.x8cv", "C:\\clip.x8cv", "bad\x00name.x8cv"):
            with self.subTest(name=name):
                self.assertIsNone(parse_trigger(name + "\n"))


if __name__ == "__main__":
    unittest.main()
