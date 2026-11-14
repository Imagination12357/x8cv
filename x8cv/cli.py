"""X8CV subcommands and terminal output; imports processors only on dispatch.

main(argv=None) returns an exit status. parse_args accepts an optional argument
list for callers/tests. Help requires only the Python standard library.
"""
import argparse
import subprocess
import sys


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m x8cv",
                                     description="Build glyph tables and preprocess videos for Xed")
    commands = parser.add_subparsers(dest="command", required=True)
    video = commands.add_parser("preprocess", help="convert video to X8CV")
    video.add_argument("input_path")
    video.add_argument("output_path")
    video.add_argument("fps", nargs="?", default="30", help="output FPS (default: 30)")
    video.add_argument("--downscale", type=int,
                       help="integer scale dividing both source cell dimensions; overrides target")
    video.add_argument("--target-glyphs", type=int,
                       help="automatic target glyph count (default: 3600; ignored with --downscale)")
    glyphs = commands.add_parser("build-glyphs", help="extract an Unscii-8 HEX glyph table")
    glyphs.add_argument("hex_path")
    glyphs.add_argument("output_path", nargs="?", help="output NPZ (default: data/glyphs_unscii.npz)")
    return parser.parse_args(argv)


def format_size(size):
    size = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.2f} {unit}"
        size /= 1024


def format_time(seconds):
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"


def _print_progress(count, elapsed, total_frames, written_bytes, frame_bytes, final=False):
    speed = count / elapsed if elapsed > 0 else 0
    raw_bytes = count * frame_bytes
    ratio = written_bytes / raw_bytes * 100 if raw_bytes else 0
    parts = []
    if total_frames:
        parts.append(f"{min(count / total_frames * 100, 100):5.1f}%")
    parts.extend((f"{count:,} frames", f"{speed:.1f} FPS",
                  f"{format_size(written_bytes)}", f"{ratio:.1f}% compressed size"))
    if total_frames and speed > 0:
        parts.append(f"ETA {format_time(max(0, total_frames - count) / speed)}")
    message = " | ".join(parts)
    print(f"\r{message}\033[K", end="\n" if final else "", file=sys.stderr, flush=True)


def _report_progress(stage, details):
    if stage == "probe":
        print("[1/3] Probing video...", flush=True)
    elif stage == "processing":
        width, height = details["width"], details["height"]
        total_frames = details["total_frames"]
        cell_size = details["cell_size"]
        print(f"  Input       : {details['input_path']}")
        print(f"  Resolution  : {details['source_width']}x{details['source_height']}")
        print(f"  Duration    : {format_time(details['duration'])}")
        print(f"  Target FPS  : {details['fps']:.3f}")
        print(f"  Downscale   : {details['downscale']}")
        print(f"  Output      : {width}x{height} cells ({width * height:,} glyphs)")
        print(f"  Cell size   : {cell_size}x{cell_size} bits")
        print(f"  Threshold   : {details['threshold']}")
        print(f"  Compression : Zstandard level {details['compression_level']}")
        print(f"  Frames (est): {total_frames if total_frames is not None else 'unknown'}")
        print("\n[2/3] Processing frames...", flush=True)
    elif stage == "progress":
        _print_progress(**details)
    elif stage == "index":
        print("\n[3/3] Writing frame index...", flush=True)


def _print_summary(result):
    count, elapsed = result["frame_count"], result["elapsed"]
    speed = count / elapsed if elapsed > 0 else 0
    print("\nCompleted!")
    print(f"  Frames      : {count:,}")
    print(f"  Duration    : {format_time(count / result['fps'])}")
    print(f"  Elapsed     : {elapsed:.2f} s")
    print(f"  Throughput  : {speed:.2f} FPS")
    print(f"  Raw size    : {format_size(result['raw_bytes'])}")
    print(f"  File size   : {format_size(result['output_bytes'])}")
    print(f"  Size ratio  : {result['output_bytes'] / result['raw_bytes'] * 100:.2f}%")
    print(f"  Output      : {result['output_path']}")


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.command == "preprocess":
            from x8cv.preprocess import preprocess

            options = {}
            if args.target_glyphs is not None:
                options["target_glyphs"] = args.target_glyphs
            result = preprocess(args.input_path, args.output_path, args.fps,
                                downscale=args.downscale, progress=_report_progress, **options)
            _print_summary(result)
        elif args.command == "build-glyphs":
            from x8cv.build_glyphs import DEFAULT_OUTPUT_PATH, build
            from x8cv.glyph_catalog import CODEPOINTS

            output = args.output_path if args.output_path is not None else DEFAULT_OUTPUT_PATH
            count = build(args.hex_path, output)
            print(f"Saved {count} unique glyphs from {len(CODEPOINTS)} codepoints to {output}")
    except KeyboardInterrupt:
        print("x8cv: cancelled", file=sys.stderr)
        return 130
    except (OSError, ValueError, ZeroDivisionError, RuntimeError, ImportError,
            subprocess.SubprocessError) as exc:
        print(f"x8cv: error: {exc}", file=sys.stderr)
        return 1
    return 0
