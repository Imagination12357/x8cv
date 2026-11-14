"""Bytes <-> zstd with one backend selected at import; no caller-side branching.

Prefer compression.zstd when importable, otherwise use ctypes/system libzstd.
Codec errors become RuntimeError; decoded size mismatches are rejected.
Used by preprocess and renderer without any extra pip dependency.
"""
try:
    from compression import zstd as _zstd
except ImportError:
    _zstd = None


if _zstd is None:
    import ctypes as C
    from ctypes.util import find_library

    _lib = C.CDLL(find_library("zstd") or "libzstd.so.1")
    _size = C.c_size_t
    for name, args, result in [
        ("ZSTD_compressBound", [_size], _size),
        ("ZSTD_compress", [C.c_void_p, _size, C.c_void_p, _size, C.c_int], _size),
        ("ZSTD_decompress", [C.c_void_p, _size, C.c_void_p, _size], _size),
        ("ZSTD_isError", [_size], C.c_uint),
        ("ZSTD_getErrorName", [_size], C.c_char_p),
    ]:
        f = getattr(_lib, name)
        f.argtypes, f.restype = args, result

    def _check(size):
        if _lib.ZSTD_isError(size):
            raise RuntimeError(_lib.ZSTD_getErrorName(size).decode())
        return size

    def _compress(data, level):
        src = C.create_string_buffer(data)
        dst = C.create_string_buffer(_check(_lib.ZSTD_compressBound(len(data))))
        n = _check(_lib.ZSTD_compress(dst, len(dst), src, len(data), level))
        return dst.raw[:n]

    def _decompress(data, expected_size):
        src = C.create_string_buffer(data)
        dst = C.create_string_buffer(expected_size)
        n = _check(_lib.ZSTD_decompress(dst, expected_size, src, len(data)))
        return dst.raw[:n]

else:
    def _compress(data, level):
        try:
            return _zstd.compress(data, level=level)
        except _zstd.ZstdError as exc:
            raise RuntimeError(str(exc)) from exc

    def _decompress(data, expected_size):
        chunks = []
        size = 0
        remaining = data
        try:
            while remaining:
                decoder = _zstd.ZstdDecompressor()
                chunk = decoder.decompress(remaining, max_length=expected_size - size + 1)
                size += len(chunk)
                if size > expected_size:
                    raise RuntimeError("Decoded frame exceeds expected size")
                if not decoder.eof:
                    raise RuntimeError("Incomplete zstd frame")
                chunks.append(chunk)
                remaining = decoder.unused_data
        except _zstd.ZstdError as exc:
            raise RuntimeError(str(exc)) from exc
        return b"".join(chunks)


def compress(data, level=1):
    return _compress(data, level)


def decompress(data, expected_size):
    if not isinstance(expected_size, int) or expected_size < 0:
        raise ValueError("Expected decoded size must be a nonnegative integer")
    if not data:
        raise RuntimeError("Empty zstd payload")
    output = _decompress(data, expected_size)
    if len(output) != expected_size:
        raise ValueError(f"Unexpected decoded frame length: {len(output)}")
    return output
