"""Xed in-place playback: filename + Enter, plain q to stop, :videos to list."""
import importlib
import sys
import time
import traceback
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GObject, GLib, Gtk, Gdk, Xed

PLUGIN_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PLUGIN_DIR.parent
for path in (PROJECT_DIR, PLUGIN_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config import SOURCE_MODULE, VIDEO_DIR, TIMER_INTERVAL_MS
from x8cv.trigger import LIST_TRIGGER, parse_trigger
from x8cv.video_catalog import list_videos

END_TEXT = "The End"


class X8CVPlayerPlugin(GObject.Object, Xed.ViewActivatable):
    __gtype_name__ = "X8CVPlayerViewPlugin"
    view = GObject.Property(type=Xed.View)

    def __init__(self):
        super().__init__()
        self._buffer = None
        self._changed_handler = None
        self._key_handler = None
        self._updating = False
        self._pending = False
        self._active = False
        self._source = None
        self._filename = None
        self._timer = None
        self._start_time = 0.0
        self._last_index = -1
        self._old_settings = None

    @staticmethod
    def _text(buffer):
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, True)

    def do_activate(self):
        self._buffer = self.view.get_buffer()
        self._active = True
        self._changed_handler = self._buffer.connect("changed", self._on_changed)
        self._key_handler = self.view.connect("key-press-event", self._on_key_press)
        # Don't auto-run a preexisting command when the plugin is enabled.

    def _on_changed(self, buffer):
        if not self._active or self._updating or self._source is not None or self._pending:
            return
        text = self._text(buffer)
        if text == LIST_TRIGGER or parse_trigger(text) is not None:
            self._pending = True
            GLib.idle_add(self._run_command)

    def _run_command(self):
        self._pending = False
        if not self._active or self._buffer is None or self._source is not None:
            return False
        text = self._text(self._buffer)
        if text == LIST_TRIGGER:
            self._show_videos()
            return False
        filename = parse_trigger(text)
        if filename is None:
            return False
        try:
            path = PROJECT_DIR / VIDEO_DIR / filename
            if not path.is_file():
                raise FileNotFoundError(f"Video file not found: {path}")
            source_type = importlib.import_module(SOURCE_MODULE).FrameSource
            source = source_type(path)
        except Exception as exc:
            traceback.print_exc()
            self._show_error(f"Could not open video: {exc}")
            return False

        self._source = source
        self._filename = filename
        try:
            self._old_settings = (
                self.view.get_editable(),
                self.view.get_wrap_mode(),
                self.view.get_show_line_numbers(),
                self._buffer.get_highlight_syntax(),
                self._buffer.get_highlight_matching_brackets(),
            )
            self.view.set_editable(False)
            self.view.set_wrap_mode(Gtk.WrapMode.NONE)
            self.view.set_show_line_numbers(False)
            self._buffer.set_highlight_syntax(False)
            self._buffer.set_highlight_matching_brackets(False)
            self._start_time = time.monotonic()
            self._last_index = -1
            # Immediately show first frame; the timer keeps time afterwards.
            if self._tick():
                self._timer = GLib.timeout_add(TIMER_INTERVAL_MS, self._tick)
        except Exception as exc:
            traceback.print_exc()
            self._finish()
            self._show_error(f"Could not start playback: {exc}")
        return False

    def _show_videos(self):
        try:
            filenames = list_videos(PROJECT_DIR / VIDEO_DIR)
        except OSError as exc:
            self._show_error(f"Could not list videos: {exc}")
            return
        body = "\n".join(filenames) if filenames else "No .x8cv files found."
        self._set_text(f"Available videos:\n{body}\n")

    def _on_key_press(self, view, event):
        if not self._active or self._source is None:
            return False
        if event.keyval != Gdk.KEY_q or event.state & Gtk.accelerator_get_default_mod_mask():
            return False
        self._finish(self._filename)
        return True

    def _set_text(self, text):
        self._buffer.begin_not_undoable_action()
        self._updating = True
        try:
            self._buffer.set_text(text)
        finally:
            try:
                self._buffer.end_not_undoable_action()
            finally:
                self._updating = False

    def _tick(self):
        if not self._active or self._source is None or self._buffer is None:
            return False
        index = int((time.monotonic() - self._start_time) * self._source.fps)
        if index >= self._source.frame_count:
            self._finish()
            return False
        if index == self._last_index:
            return True
        try:
            self._set_text(self._source.get_frame(index))
            self._last_index = index
        except Exception as exc:
            traceback.print_exc()
            self._finish()
            self._show_error(f"Playback failed: {exc}")
            return False
        return True

    def _finish(self, text=END_TEXT):
        # Keep _source non-None until the final text is written and source closed.
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        if self._source is not None:
            try:
                if self._buffer is not None:
                    self._set_text(text)
                    self._buffer.place_cursor(self._buffer.get_end_iter())
            finally:
                self._source.close()
                self._source = None
        self._filename = None
        if self._old_settings is not None and self._buffer is not None:
            (editable, wrap, lines, syntax, brackets) = self._old_settings
            self.view.set_editable(editable)
            self.view.set_wrap_mode(wrap)
            self.view.set_show_line_numbers(lines)
            self._buffer.set_highlight_syntax(syntax)
            self._buffer.set_highlight_matching_brackets(brackets)
        self._old_settings = None
        self._last_index = -1

    def do_deactivate(self):
        self._active = False
        self._pending = False
        self._finish()
        if self._key_handler is not None:
            self.view.disconnect(self._key_handler)
        self._key_handler = None
        if self._buffer is not None and self._changed_handler is not None:
            self._buffer.disconnect(self._changed_handler)
        self._changed_handler = None
        self._buffer = None

    def _show_error(self, message):
        window = self.view.get_toplevel()
        if not isinstance(window, Gtk.Window):
            print(f"X8CV Player: {message}", file=sys.stderr)
            return
        dialog = Gtk.MessageDialog(
            transient_for=window,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="X8CV Player",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
