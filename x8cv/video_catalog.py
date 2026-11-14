"""List playable filenames directly inside a video directory, sorted by name.

Uses pathlib and trigger parsing; no GTK or video decoding. Directory errors
propagate to the caller. Each call reads the directory again without a cache.
"""
from pathlib import Path

from x8cv.trigger import parse_trigger


def list_videos(directory):
    return sorted(entry.name for entry in Path(directory).iterdir()
                  if entry.is_file() and parse_trigger(entry.name + "\n") is not None)
