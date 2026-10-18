"""DC6 pixel encoding (see filetype_dc6.md §3).

Opcodes: 0x80 = end of line, 0x81..0xFF = skip (c & 0x7F) transparent pixels,
0x01..0x7F = literal run of c palette indices. Rows are stored bottom-up.
"""

import numpy as np

EOL = 0x80
MAX_RUN = 0x7F


def decode_frame(data: bytes, width: int, height: int, flip: int = 0) -> tuple[np.ndarray, list[str]]:
    """Decode RLE data into a (height, width) uint8 index array (row 0 = top).

    Never raises on bad data: out-of-bounds pixels are clipped and reported as warnings.
    """
    px = np.zeros((height, width), np.uint8)
    warnings: list[str] = []
    x, y = 0, (height - 1 if flip == 0 else 0)
    step = -1 if flip == 0 else 1
    i, n = 0, len(data)
    overrun = zero_ops = eols = 0
    while i < n:
        c = data[i]
        i += 1
        if c == EOL:
            x, y = 0, y + step
            eols += 1
        elif c & 0x80:
            x += c & MAX_RUN
        elif c == 0:
            zero_ops += 1
        else:
            run = data[i : i + c]
            i += c
            k = max(0, min(len(run), width - x)) if 0 <= y < height else 0
            if k:
                px[y, x : x + k] = np.frombuffer(run[:k], np.uint8)
            overrun += len(run) - k
            x += c
    if overrun:
        warnings.append(f"{overrun} pixel(s) outside the frame area were ignored")
    if zero_ops:
        warnings.append(f"{zero_ops} invalid 0x00 opcode(s)")
    if eols != height:
        warnings.append(f"{eols} line ends for a frame height of {height}")
    return px, warnings


def encode_frame(px: np.ndarray) -> bytes:
    """Canonical encoder: reproduces Blizzard's byte layout exactly.

    Per row (bottom to top): trailing transparency is dropped, skips > 127 use 0xFF chains,
    literal runs are split at 127, and every row (also empty ones) ends with 0x80.
    """
    height = px.shape[0]
    out = bytearray()
    for y in range(height - 1, -1, -1):
        row = px[y]
        nz = np.flatnonzero(row)
        if nz.size:
            last = int(nz[-1]) + 1
            r = row[:last].tobytes()
            x = 0
            while x < last:
                start = x
                if r[x] == 0:
                    while x < last and r[x] == 0:
                        x += 1
                    skip = x - start
                    while skip > MAX_RUN:
                        out.append(0xFF)
                        skip -= MAX_RUN
                    out.append(EOL | skip)
                else:
                    while x < last and r[x] != 0 and x - start < MAX_RUN:
                        x += 1
                    out.append(x - start)
                    out += r[start:x]
        out.append(EOL)
    return bytes(out)
