# X8CV

Xed 8x8 Cell Video. Build glyph tables, convert videos, and play them in Xed.

Play a video as Unicode cells inside Xed. In an otherwise empty document,
type its `.x8cv` filename and press Enter. The plugin plays the video in
that document, then displays `The End`. Playback has no audio.
Press `q` during playback to stop, or use `:videos` followed by Enter to list files.

https://github.com/user-attachments/assets/3e41fcb9-992f-44ca-98e0-401696dee6fc

This started as a Bad Apple demo. The player and its `x8cv` Python package also
work with other videos that meet the source size requirements below.

Source width and height must be positive multiples of 8. The preprocessor
chooses an integer downscale aiming for 3,600 cells, with a limit of 10,000.
The plugin reads X8CV (Xed 8x8 Cell Video) version 1 files (`.x8cv`).

## Requirements

On Debian-based Linux distributions with APT:

```bash
sudo apt install xed ffmpeg python3-numpy python3-gi libzstd1
```

The codec uses Python's `compression.zstd` when available (added in Python 3.14).
Otherwise it loads the system `libzstd` installed above. It checks module
availability once when imported; no extra pip package or setting is needed.

Install Unscii-8 from [the official Unscii project](https://viznut.fi/unscii/)
and select it in Xed Preferences -> Fonts & Colors. Use the matching
`unscii-8.hex` bitmap source to build the glyph table. The renderer assumes square
8x8 cells; another font may display the same characters differently.

Run the commands below from the project root.
Use `python3 -m x8cv --help` to list commands, or add `--help` after
`preprocess` or `build-glyphs` for their arguments.

## Build the glyph table

Download `unscii-8.hex` from the
[official repository](https://github.com/viznut/unscii/blob/master/fontfiles/unscii-8.hex).
The builder reads the HEX bitmap source:

```bash
python3 -m x8cv build-glyphs /path/to/unscii-8.hex
```

This creates `data/glyphs_unscii.npz`. To save it elsewhere, pass an output path:

```bash
python3 -m x8cv build-glyphs /path/to/unscii-8.hex /path/to/glyphs.npz
```

`x8cv/glyph_catalog.py` lists 427 candidate characters in priority order:

1. U+0020 (space), U+2580-U+2590, and U+2594-U+259F, in that order.
2. U+1FB00-U+1FB8B, excluding U+1FB7C-U+1FB7F and U+1FB81.
3. U+2800-U+28FF: Braille patterns, drawn as filled 2x4 block mosaics in Unscii-8.
4. U+25E2-U+25E5: filled corner triangles.
5. U+1FB9A-U+1FB9B: opposing triangular combinations.

The builder extracts every mask from HEX and removes duplicate masks, keeping
the first character for each. It stops before writing the output if a required
glyph is missing or has a size other than 8x8.

You need to supply the font and build the glyph table. Playback requires the
NPZ; if it is missing, the plugin shows the build command. There is no fallback
glyph set. Restart Xed after rebuilding the table.

The NPZ contains `chars` (a one-dimensional NumPy U1 array) and `masks` (a
little-endian u64 array of the same length). The loader rejects empty arrays,
invalid shapes or types, and duplicate characters or masks.

## Preprocess video

```bash
python3 -m x8cv preprocess /path/to/video.mp4 data/badapple.x8cv 30
```

The optional positional FPS argument defaults to 30. To change the automatic
target or choose a scale yourself:

```bash
python3 -m x8cv preprocess input.mp4 data/badapple.x8cv --target-glyphs 5000
python3 -m x8cv preprocess input.mp4 data/badapple.x8cv 30 --downscale 3
```

For source dimensions W and H, both divisible by 8, let `w = W // 8` and
`h = H // 8`. Automatic selection considers every positive divisor `d` of
`gcd(w, h)`. Each candidate produces `(w // d) x (h // d)` cells. Candidates
over 10,000 cells are discarded; the closest count to `--target-glyphs` wins.
Ties prefer the larger output. There is no minimum cell count. If no candidate
meets the limit, preprocessing stops with an error.

`--downscale` skips automatic selection and ignores `--target-glyphs`. It must
be a positive integer dividing both `w` and `h`, and the output must still fit
within 10,000 cells. Invalid manual scales produce an error. The preprocessor
prints the chosen scale and output cell dimensions before processing frames.

For example, 1920x1080 with the default target selects `d=3`, producing 80x45
cells. A 1280x720 source selects `d=2`, also producing 80x45 cells.

The preprocessor converts each frame to grayscale and marks pixels below 128
as dark. A `d x d` source region becomes one output pixel, dark only when more
than half its source pixels are dark. Ties are light; `d=1` preserves the
thresholded pixels. Every 8x8 output pixels form a cell stored as a little-endian
u64 mask. You can preprocess video before building the glyph table.

Each frame is compressed with Zstandard level 1. During processing, the
preprocessor reports frame count, processing FPS, and compressed size. It also
estimates percentage complete and ETA when the input duration is available,
then prints final statistics.

Save generated videos in `data/`. To use another directory, set `VIDEO_DIR`
in `xed/config.py`; the path is resolved from the project directory.
You can keep multiple `.x8cv` files there and select each by its filename.

## Enable the Xed plugin

```bash
mkdir -p ~/.local/share/xed/plugins
ln -s "$(pwd)/xed" ~/.local/share/xed/plugins/x8cv
```

If a plugin link already exists, check that it points to this project's
`xed/` directory. Keep one link to the plugin directory. If you move the
project, update the link target before restarting Xed.
Restart Xed and enable `X8CV Player` under Edit -> Preferences -> Plugins.
For `data/badapple.x8cv`, type this in an empty document:

```text
badapple.x8cv
```

Then press Enter. The entire document must be exactly `badapple.x8cv\n`:
the filename, including the `.x8cv` extension, followed by one newline.
Use the exact filename, including spaces and letter case. Unicode filenames
are supported. The extension must be lowercase `.x8cv`. Enter the filename
only, without quotes, directory paths, or additional lines.

To play `data/demo.x8cv`, enter `demo.x8cv` and press Enter instead.
The plugin checks the named file when you submit the command, so you can
add videos while Xed is open and play them without restarting it. If the
file is missing, the plugin shows an error and leaves the document unchanged.

To see the available filenames, replace the document contents with `:videos`
and press Enter. The plugin reads the video directory and writes a sorted list
in the same document:

```text
Available videos:
badapple.x8cv
demo.x8cv
```

Keep only the filename you want, then press Enter to play it. The list contains
files directly inside `VIDEO_DIR` with names accepted by the filename trigger.
It does not scan subdirectories or decode videos. An empty directory produces
`No .x8cv files found.` below the heading. If the directory cannot be read, the
plugin shows an error and leaves the command in place.

During playback, the plugin makes the view read-only and turns off line
wrapping, line numbers, and highlighting. Press lowercase `q` without modifier
keys while the playing view has focus to stop. The plugin closes the video,
removes its timer, restores the previous settings, and puts the filename back
without a newline. The cursor is placed at its end, so Enter replays the video.
Outside playback, `q` is ordinary input; shortcuts such as `Ctrl+Q` pass through
to Xed.

When playback reaches the end, the plugin writes `The End` and restores the
previous settings. To replay or choose another video, replace that text with a
filename and press Enter. Closing the tab stops playback; disabling the plugin
during playback writes `The End`.

The plugin watches buffer changes, so enabling it with the command already in
the document will not start playback. It uses one `Xed.ViewActivatable` instance
per view. Filename parsing does not access the filesystem; the deferred
playback callback reads the current command and checks that file directly,
without a directory index. A GTK timer polls every 10 ms and selects the
frame from monotonic elapsed time, skipping late frames. Programmatic text
updates do not dispatch commands, so displaying a one-file list cannot start
playback.

Use a disposable document. Playback replaces its contents, and saving the
document saves the rendered text.

## Project structure

| File | Role |
| --- | --- |
| `x8cv/__main__.py` | Entry point for `python3 -m x8cv` |
| `x8cv/cli.py` | Subcommands, argument parsing, terminal progress, summaries, and errors |
| `x8cv/glyph_catalog.py` | Ordered code points; no bitmap generation or I/O |
| `x8cv/build_glyphs.py` | HEX + catalog -> deduplicated NPZ; returns glyph count or raises an error |
| `x8cv/glyphs.py` | NPZ -> validated character/mask arrays; depends on NumPy |
| `x8cv/format.py` | X8CV constants and header reader; standard library only |
| `x8cv/preprocess.py` | Scale selection and video -> X8CV; returns statistics and reports progress through a callback |
| `x8cv/zstd_codec.py` | Bytes <-> zstd frames; standard-library backend with ctypes/libzstd fallback |
| `x8cv/renderer.py` | Indexed X8CV frames + glyph arrays -> Unicode text; no GTK |
| `x8cv/trigger.py` | Filename-plus-newline parsing; no filesystem or GTK dependency |
| `x8cv/video_catalog.py` | Sorted playable filenames from the video directory; no GTK or decoding |
| `xed/config.py` | Renderer module, video directory, and timer interval |
| `xed/x8cv_player.py` | Document commands, q key handling, and timed playback through `FrameSource` |
| `xed/x8cv_player.plugin` | Xed plugin registration |
| `data/` | Generated NPZ and X8CV files; separate from source |
| `tests/` | Glyph extraction, filename parsing, downscale selection, encoding, rendering, codec, and seek tests |

See [the Python API](docs/api.md) for library usage and
[the X8CV format](docs/format.md) for the binary specification.

## Testing on Linux

On Linux, run:

```bash
python3 -m x8cv --help
python3 -m unittest discover -s tests -v
python3 -m x8cv build-glyphs /path/to/unscii-8.hex
python3 -m x8cv preprocess /path/to/video.mp4 data/badapple.x8cv 30
```

The tests need NumPy and libzstd; codec tests also exercise the ctypes fallback
when the standard backend is available. They create synthetic HEX/NPZ fixtures and
temporary videos, so you can run them before building the real glyph table
or video, without opening Xed. Then restart Xed and check:

- Press plain `q` during playback. Confirm that the exact filename returns
  without a newline, view settings are restored, and Enter replays the video.
  Outside playback, check ordinary `q` input. During playback, confirm modified
  keys such as `Ctrl+Q` retain their Xed behavior.
- Submit `:videos` with zero, one, and several files. A one-file list must not
  start playback. Add a video and request the list again to check the refresh.
- Different filenames followed by Enter play the corresponding files in the
  same document. Add a video while Xed is open and confirm it can be played.
  Check missing-file errors, completion, replay, closing the tab, and disabling
  the plugin.
- The rendered shapes match the installed Unscii-8 font. Check whether the new
  glyphs improve contours or introduce visual artifacts.
- Playback stays smooth with the larger glyph table. Trim the candidate set
  if rendering becomes too slow.
- Try different source sizes, automatic targets, and manual scales. Confirm
  that the reported dimensions match the displayed rows and columns, including
  even scales and a one-cell output.
- Temporarily remove the NPZ and confirm that playback shows the build command.

Plugin control tests use GTK doubles to check command and cleanup logic. Actual
key delivery, focus behavior, and restored cursor placement need the Xed check.
