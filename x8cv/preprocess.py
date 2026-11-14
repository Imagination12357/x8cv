"""Video -> variable-resolution X8CV v1 (zstd level 1).

Inputs: video/output paths, FPS, optional downscale and target glyph count.
Requires FFmpeg/ffprobe, NumPy, and the zstd codec; no font or GTK dependency.
Returns conversion statistics. Optional progress(stage, details) receives probe,
processing, progress, and index notifications; this module does not print.
The command-line entry point is python3 -m x8cv preprocess.
"""
import subprocess
import time
from fractions import Fraction
from math import gcd, isqrt
from pathlib import Path

import numpy as np

from x8cv.format import (
    MAGIC, VERSION, CELL_SIZE, CELL_BYTES, MAX_GLYPHS, HEADER, CHUNK_LENGTH, OFFSET,
    validate_dimensions,
)
from x8cv.zstd_codec import compress

DEFAULT_TARGET_GLYPHS = 3600
THRESHOLD = 128
COMPRESSION_LEVEL = 1
PROGRESS_INTERVAL = 0.5


def select_downscale(width, height, downscale=None, target_glyphs=DEFAULT_TARGET_GLYPHS):
    """Return (integer scale, cell columns, cell rows) for the source dimensions."""
    if (not isinstance(width, int) or not isinstance(height, int)
            or width <= 0 or height <= 0
            or width % CELL_SIZE or height % CELL_SIZE):
        raise ValueError(f"Source dimensions must be positive integer multiples of {CELL_SIZE}")
    w, h = width // CELL_SIZE, height // CELL_SIZE
    if downscale is not None:
        if (not isinstance(downscale, int) or downscale <= 0
                or w % downscale or h % downscale):
            raise ValueError("Downscale must be a positive integer dividing both cell dimensions")
        columns, rows = w // downscale, h // downscale
        validate_dimensions(columns, rows)
        return downscale, columns, rows

    if not isinstance(target_glyphs, int):
        raise ValueError("Target glyph count must be an integer")
    common = gcd(w, h)
    divisors = set()
    for factor in range(1, isqrt(common) + 1):
        if common % factor == 0:
            divisors.update((factor, common // factor))
    candidates = [(d, w // d, h // d) for d in divisors
                  if (w // d) * (h // d) <= MAX_GLYPHS]
    if not candidates:
        raise ValueError(f"No integer downscale produces at most {MAX_GLYPHS} glyphs")
    return min(candidates, key=lambda choice: (
        abs(choice[1] * choice[2] - target_glyphs), -choice[1] * choice[2],
    ))


def probe_video(path):
    output = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "default=noprint_wrappers=1", str(path)],
        text=True,
    )
    info = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    width, height = int(info["width"]), int(info["height"])
    try:
        duration = float(info["duration"])
        if not np.isfinite(duration) or duration <= 0:
            duration = None
    except (KeyError, ValueError):
        duration = None
    return width, height, duration


def encode_frame(raw: bytes, source_width, source_height, downscale) -> bytes:
    downscale, width, height = select_downscale(source_width, source_height, downscale)
    if len(raw) != source_width * source_height:
        raise ValueError("Incomplete source frame")
    image = np.frombuffer(raw, dtype=np.uint8).reshape(source_height, source_width)
    binary = image < THRESHOLD
    dark_count = binary.reshape(height * CELL_SIZE, downscale,
                                width * CELL_SIZE, downscale).sum(axis=(1, 3))
    down = dark_count > (downscale * downscale) // 2
    cells = down.reshape(height, CELL_SIZE, width, CELL_SIZE).transpose(0, 2, 1, 3)
    data = np.packbits(cells.reshape(height * width, CELL_SIZE * CELL_SIZE), axis=1,
                       bitorder="little").tobytes()
    assert len(data) == width * height * CELL_BYTES
    return data


def read_frame(stream, source_bytes):
    chunks = []
    remaining = source_bytes
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if remaining == source_bytes:
                return None
            raise ValueError("Incomplete frame from FFmpeg")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def preprocess(input_path, output_path, fps=30, downscale=None,
               target_glyphs=DEFAULT_TARGET_GLYPHS, progress=None):
    """Write an X8CV file and return frame_count/fps/elapsed/byte/path statistics.

    progress(stage, details) is optional. The processing stage supplies source
    and selected output dimensions/settings. Progress updates supply count,
    elapsed, total_frames, written_bytes, frame_bytes, and final.
    FFmpeg's stderr is inherited for external decoder diagnostics.
    """
    input_path, output_path = Path(input_path), Path(output_path)
    rate = Fraction(str(fps)).limit_denominator(100000)
    if rate <= 0 or rate.numerator > 0xFFFFFFFF or rate.denominator > 0xFFFFFFFF:
        raise ValueError("Invalid FPS")

    if progress is not None:
        progress("probe", {})
    source_width, source_height, duration = probe_video(input_path)
    downscale, width, height = select_downscale(
        source_width, source_height, downscale, target_glyphs,
    )
    source_bytes = source_width * source_height
    frame_bytes = width * height * CELL_BYTES
    total_frames = round(duration * float(rate)) if duration is not None else None
    if progress is not None:
        progress("processing", {
            "input_path": input_path, "source_width": source_width,
            "source_height": source_height, "duration": duration, "fps": float(rate),
            "downscale": downscale, "width": width, "height": height,
            "cell_size": CELL_SIZE, "threshold": THRESHOLD,
            "compression_level": COMPRESSION_LEVEL, "total_frames": total_frames,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
           "-i", str(input_path), "-map", "0:v:0", "-an", "-sn",
           "-vf", f"fps={rate.numerator}/{rate.denominator},format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    count, offsets, compressed_bytes = 0, [], 0
    start = last_progress = time.monotonic()

    try:
        with output_path.open("wb") as target:
            target.write(HEADER.pack(MAGIC, VERSION, width, height,
                                     rate.numerator, rate.denominator, 0, 0))
            while True:
                raw = read_frame(process.stdout, source_bytes)
                if raw is None:
                    break
                payload = compress(encode_frame(raw, source_width, source_height, downscale),
                                   level=COMPRESSION_LEVEL)
                offsets.append(target.tell())
                target.write(CHUNK_LENGTH.pack(len(payload)))
                target.write(payload)
                count += 1
                compressed_bytes += len(payload)
                now = time.monotonic()
                if progress is not None and now - last_progress >= PROGRESS_INTERVAL:
                    progress("progress", {
                        "count": count, "elapsed": now - start,
                        "total_frames": total_frames, "written_bytes": compressed_bytes,
                        "frame_bytes": frame_bytes, "final": False,
                    })
                    last_progress = now
            if process.wait() != 0:
                raise RuntimeError("FFmpeg failed")
            if count == 0:
                raise ValueError("No frames were decoded")
            if progress is not None:
                progress("progress", {
                    "count": count, "elapsed": time.monotonic() - start,
                    "total_frames": total_frames, "written_bytes": compressed_bytes,
                    "frame_bytes": frame_bytes, "final": True,
                })
                progress("index", {})
            index_offset = target.tell()
            for offset in offsets:
                target.write(OFFSET.pack(offset))
            target.seek(0)
            target.write(HEADER.pack(MAGIC, VERSION, width, height,
                                     rate.numerator, rate.denominator, count, index_offset))
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        output_path.unlink(missing_ok=True)
        raise
    finally:
        process.stdout.close()

    elapsed = time.monotonic() - start
    output_bytes = output_path.stat().st_size
    raw_bytes = count * frame_bytes
    return {
        "frame_count": count, "fps": float(rate), "elapsed": elapsed,
        "raw_bytes": raw_bytes, "output_bytes": output_bytes, "output_path": output_path,
    }
