"""Plugin state transitions with GTK doubles; actual key delivery needs Xed."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def load_plugin():
    gi = types.ModuleType("gi")
    gi.require_version = lambda *args: None
    repository = types.ModuleType("gi.repository")
    repository.GObject = types.SimpleNamespace(
        Object=type("Object", (), {}), Property=lambda **kwargs: None,
    )
    repository.Xed = types.SimpleNamespace(View=object, ViewActivatable=type("ViewActivatable", (), {}))
    repository.GLib = types.SimpleNamespace(idle_add=Mock(return_value=1),
                                          timeout_add=Mock(return_value=2), source_remove=Mock())
    repository.Gdk = types.SimpleNamespace(KEY_q=ord("q"))
    repository.Gtk = types.SimpleNamespace(WrapMode=types.SimpleNamespace(NONE=0),
                                          accelerator_get_default_mod_mask=lambda: 1 | 4 | 8 | (1 << 26))
    gi.repository = repository
    config = types.ModuleType("config")
    config.SOURCE_MODULE = "x8cv.renderer"
    config.VIDEO_DIR = "data"
    config.TIMER_INTERVAL_MS = 10
    path = Path(__file__).resolve().parents[1] / "xed" / "x8cv_player.py"
    spec = importlib.util.spec_from_file_location("plugin_control_test_instance", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"gi": gi, "gi.repository": repository, "config": config}), \
            patch.object(sys, "path", sys.path.copy()):
        spec.loader.exec_module(module)
    return module


class Buffer:
    def __init__(self):
        self.text = ""
        self.cursor = None
        self.changed = None
        self.syntax = True
        self.brackets = True

    def connect(self, signal, callback):
        self.changed = callback
        return 1

    def disconnect(self, handler):
        self.changed = None

    def get_bounds(self):
        return 0, len(self.text)

    def get_text(self, *args):
        return self.text

    def set_text(self, text):
        self.text = text
        if self.changed:
            self.changed(self)

    def begin_not_undoable_action(self):
        pass

    def end_not_undoable_action(self):
        pass

    def get_end_iter(self):
        return len(self.text)

    def place_cursor(self, position):
        self.cursor = position

    def get_highlight_syntax(self):
        return self.syntax

    def get_highlight_matching_brackets(self):
        return self.brackets

    def set_highlight_syntax(self, value):
        self.syntax = value

    def set_highlight_matching_brackets(self, value):
        self.brackets = value


class PluginControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_plugin()

    def setUp(self):
        self.module.GLib.idle_add.reset_mock()
        self.module.GLib.timeout_add.reset_mock()
        self.module.GLib.source_remove.reset_mock()
        self.buffer = Buffer()
        self.view = Mock()
        self.view.get_buffer.return_value = self.buffer
        self.view.connect.return_value = 23
        self.view.get_editable.return_value = True
        self.view.get_wrap_mode.return_value = 7
        self.view.get_show_line_numbers.return_value = True
        self.plugin = self.module.X8CVPlayerPlugin()
        self.plugin.view = self.view
        self.plugin._show_error = Mock()
        self.plugin.do_activate()

    def arm_playback(self):
        self.source = types.SimpleNamespace(close=Mock())
        self.plugin._source = self.source
        self.plugin._filename = "badapple.x8cv"
        self.plugin._timer = 12
        self.plugin._old_settings = (True, 7, True, True, True)
        self.buffer.text = "rendered frame"

    def test_plain_q_restores_filename_without_retriggering(self):
        self.arm_playback()
        self.assertTrue(self.plugin._on_key_press(self.view, types.SimpleNamespace(keyval=ord("q"), state=0)))
        self.assertEqual(self.buffer.text, "badapple.x8cv")
        self.assertEqual(self.buffer.cursor, len("badapple.x8cv"))
        self.source.close.assert_called_once_with()
        self.module.GLib.source_remove.assert_called_once_with(12)
        self.assertIsNone(self.plugin._source)
        self.assertIsNone(self.plugin._filename)
        self.assertIsNone(self.plugin._timer)
        self.view.set_editable.assert_called_with(True)
        self.view.set_wrap_mode.assert_called_with(7)
        self.view.set_show_line_numbers.assert_called_with(True)
        self.module.GLib.idle_add.assert_not_called()
        self.buffer.set_text("badapple.x8cv\n")
        self.module.GLib.idle_add.assert_called_once()

    def test_modified_q_and_other_keys_propagate(self):
        self.arm_playback()
        for keyval, state in ((ord("q"), 4), (ord("q"), 8), (ord("q"), 1),
                              (ord("q"), 1 << 26), (ord("Q"), 0), (ord("x"), 0)):
            self.assertFalse(self.plugin._on_key_press(self.view, types.SimpleNamespace(keyval=keyval, state=state)))
        self.source.close.assert_not_called()

    def test_q_without_playback_propagates(self):
        self.assertFalse(self.plugin._on_key_press(self.view, types.SimpleNamespace(keyval=ord("q"), state=0)))

    def test_natural_finish_keeps_end_text(self):
        self.arm_playback()
        self.plugin._finish()
        self.assertEqual(self.buffer.text, "The End")

    def test_deactivation_disconnects_key_handler_and_stops(self):
        self.arm_playback()
        self.plugin.do_deactivate()
        self.view.disconnect.assert_called_once_with(23)
        self.source.close.assert_called_once_with()
        self.assertIsNone(self.plugin._key_handler)
        self.assertIsNone(self.buffer.changed)

    def test_single_file_listing_cannot_start_playback(self):
        self.buffer.text = ":videos\n"
        with patch.object(self.module, "list_videos", return_value=["only.x8cv"]):
            self.plugin._run_command()
        self.assertEqual(self.buffer.text, "Available videos:\nonly.x8cv\n")
        self.module.GLib.idle_add.assert_not_called()
        self.assertIsNone(self.plugin._source)

    def test_internal_writes_do_not_dispatch_commands(self):
        self.plugin._set_text("only.x8cv\n")
        self.module.GLib.idle_add.assert_not_called()
        self.plugin._set_text(":videos\n")
        self.module.GLib.idle_add.assert_not_called()

    def test_empty_list_and_directory_failure(self):
        self.buffer.text = ":videos\n"
        with patch.object(self.module, "list_videos", return_value=[]):
            self.plugin._run_command()
        self.assertEqual(self.buffer.text, "Available videos:\nNo .x8cv files found.\n")
        self.buffer.text = ":videos\n"
        with patch.object(self.module, "list_videos", side_effect=PermissionError("denied")):
            self.plugin._run_command()
        self.assertEqual(self.buffer.text, ":videos\n")
        self.plugin._show_error.assert_called_once()

    def test_dispatch_rereads_pending_command(self):
        self.buffer.set_text(":videos\n")
        self.buffer.text = "ordinary text"
        with patch.object(self.module, "list_videos") as listing:
            self.plugin._run_command()
        listing.assert_not_called()
        self.plugin._pending = True
        self.buffer.text = ":videos\n"
        self.plugin._active = False
        with patch.object(self.module, "list_videos") as listing:
            self.plugin._run_command()
        listing.assert_not_called()

    def test_playback_retains_filename_for_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "clip.x8cv").write_bytes(b"fixture")
            source = types.SimpleNamespace(close=Mock())
            factory = Mock(return_value=source)
            self.buffer.text = "clip.x8cv\n"
            with patch.object(self.module, "PROJECT_DIR", root), \
                    patch.object(self.module, "VIDEO_DIR", "."), \
                    patch.object(self.module.importlib, "import_module",
                                 return_value=types.SimpleNamespace(FrameSource=factory)), \
                    patch.object(self.plugin, "_tick", return_value=True):
                self.plugin._run_command()
            factory.assert_called_once_with(root / "clip.x8cv")
            self.assertEqual(self.plugin._filename, "clip.x8cv")
            self.assertIs(self.plugin._source, source)


if __name__ == "__main__":
    unittest.main()
