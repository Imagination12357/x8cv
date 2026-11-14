# Python API

`cli.py` imports a processing module after selecting its command, so help does
not require NumPy or a zstd backend. The processing modules can also be imported
directly. For example:

```python
from x8cv.preprocess import preprocess

def report(stage, details):
    if stage == "progress":
        print(details["count"], "frames processed")

result = preprocess("input.mp4", "data/badapple.x8cv", progress=report)
print(result["frame_count"])
```

The optional callback receives `probe`, `processing`, `progress`, and `index`
stages. Without it, the library does not print progress. FFmpeg's own error
diagnostics still go to stderr. The returned statistics contain `frame_count`,
`fps`, `elapsed`, `raw_bytes`, `output_bytes`, and `output_path`.
`build(hex_path, output=None)` in `x8cv.build_glyphs` returns the unique glyph
count; missing or wrong-size code points are included in its exception message.
The CLI prints those errors and returns a nonzero exit status.

`FrameSource(path, glyph_path=None)` loads the glyph table once when created.
It reads cell dimensions from the video header and exposes `width`, `height`,
`fps`, `frame_count`, `get_frame(index)`, and `close()`. The default
glyph path is `data/glyphs_unscii.npz`, relative to the project root.

The renderer uses NumPy to compare each cell with the glyph masks by Hamming
distance. Ties go to the first glyph in catalog order. It uses `bitwise_count`
where available and a byte popcount lookup table on NumPy 1.x. Each contiguous
row of U1 characters is viewed as a `U{width}` string using the file's cell width.
