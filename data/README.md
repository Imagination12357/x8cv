# Generated data

This directory holds local build outputs, not Python source:

- `glyphs_unscii.npz`: generated from the matching Unscii-8 HEX by
  `python3 -m x8cv build-glyphs /path/to/unscii-8.hex`.
- `badapple.x8cv`: generated from a video whose dimensions are multiples of 8 by
  `python3 -m x8cv preprocess /path/to/video.mp4 data/badapple.x8cv 30`.

Run commands from the project root. Neither output nor the font source is
bundled. Type a video's filename, such as `badapple.x8cv`, in an empty Xed
document and press Enter to play it. The plugin looks in the `VIDEO_DIR`
configured in `xed/config.py` (default: `data`). The default glyph path is
resolved here by `x8cv/glyphs.py`.

Use `python3 -m x8cv --help` to list the preprocessing and glyph-building commands.

Enter `:videos` followed by Enter to list the filenames in the document.
Keep one filename and press Enter to play it. During playback, plain `q` stops
the video and restores its filename without a newline; Enter plays it again.

The default automatic downscale aims for 3,600 cells and never exceeds 10,000.
Use `--target-glyphs N` for a different target or `--downscale D` for a valid
integer scale. The X8CV header records the selected cell width and height.

The glyph table and video are independent: changing character candidates only
requires rebuilding the NPZ. Videos must use the X8CV v1 format.
