# X8CV version 1 format

All integer fields are unsigned little-endian. The 34-byte header is
`struct.Struct("<4sHHHIIQQ")`:

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | Magic `X8CV` |
| 4 | u16 | Version, currently 1 |
| 6 | u16 | Width in cells, positive |
| 8 | u16 | Height in cells, positive |
| 10 | u32 | FPS numerator |
| 14 | u32 | FPS denominator |
| 18 | u64 | Frame count |
| 26 | u64 | Offset of trailing frame index |

Each frame is a u32 compressed-payload length followed by an independent zstd
payload. Its decoded size is `width x height x 8` bytes, read using the header's
cell dimensions. The cell count must be at most 10,000.
Cells are in row-major order; bit 0 is the top-left pixel and bit 63 is the
bottom-right pixel. The final index contains one absolute u64 frame offset per
frame, so the reader can seek directly to any frame.

X8CV stores cell masks. You can change the output characters by rebuilding
the glyph table without reprocessing the video.
