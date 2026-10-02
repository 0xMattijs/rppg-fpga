"""The ROI grid's cells (Phase 6): GRID lines from the board, and the files
capture.py keeps them in.

The board splits the ROI into 4 x 4 cells and sums the skin pixels in each
(firmware/include/grid.h). capture.py writes them next to the CSV, with the
extension .grid: a CSV with the frame and, per cell, the red, green, and blue
sums and the pixel count.
"""
import base64

import numpy as np

CELLS = 16
HEADER = "frame," + ",".join(f"{c}{k}" for k in range(CELLS) for c in "rgbn")


def decode(line):
    """(frame, array of 16 x 4: r, g, b sums and count) from a GRID line,
    or None if the line is damaged."""
    f = line.split()
    if len(f) != 3 or f[0] != "GRID" or not f[1].isdigit():
        return None
    try:
        raw = base64.b64decode(f[2], validate=True)
    except ValueError:
        return None
    if len(raw) != 11 * CELLS:
        return None
    b = np.frombuffer(raw, np.uint8).reshape(CELLS, 11).astype(np.int64)
    rgb = b[:, 0:9].reshape(CELLS, 3, 3) @ np.array([1 << 16, 1 << 8, 1])
    n = b[:, 9] << 8 | b[:, 10]
    return int(f[1]), np.column_stack([rgb, n])


def row(frame, cells):
    """One line of a .grid file."""
    return f"{frame}," + ",".join(str(v) for v in cells.ravel())


def load(path):
    """(frames, array of frames x 16 x 4) from a .grid file."""
    d = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.int64, ndmin=2)
    return d[:, 0], d[:, 1:].reshape(len(d), CELLS, 4)
