"""Check the board's BPM estimates against the host build of the same code.

capture.py saves the frames as session.csv and the board's estimates as
session.est. This script runs firmware/test/host_rppg over session.csv and
compares each estimate. The firmware restarts its estimates at the first
recorded frame, so both see the same frames.

    python -m rppg.check_board ../data/session.csv
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

from .check_firmware import TEST_DIR, run_c

# The board prints BPM with 2 decimals and quality with 4. Beyond that, the
# board's soft-float libm and the PC's differ in the last bits.
BPM_TOL = 0.02
QUALITY_TOL = 1e-3


def load_est(path):
    """Return (rows, us): rows of (frame, bpm_raw, bpm, quality) and the
    time each estimate took on the board."""
    d = np.loadtxt(path, usecols=(1, 2, 3, 4, 5), ndmin=2)
    return d[:, :4], d[:, 4]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("csv", type=Path)
    p.add_argument("--est", type=Path, help="default: the CSV path with .est")
    args = p.parse_args()

    subprocess.run(["make", "-s", "-C", TEST_DIR], check=True)
    board, us = load_est(args.est or args.csv.with_suffix(".est"))
    host, _ = run_c(args.csv)

    # The board's last estimate can be missing from the CSV's end, or the
    # reverse, depending on when capture stopped. Compare the frames in both.
    common = np.intersect1d(board[:, 0], host[:, 0])
    if len(common) == 0:
        sys.exit("no estimates in common; was the .est file recorded with this CSV?")
    b = board[np.isin(board[:, 0], common)]
    h = host[np.isin(host[:, 0], common)]
    only = len(board) + len(host) - 2 * len(common)

    bpm_diff = np.max(np.abs(b[:, 1:3] - h[:, 1:3]))
    q_diff = np.max(np.abs(b[:, 3] - h[:, 3]))
    ok = bpm_diff <= BPM_TOL and q_diff <= QUALITY_TOL

    print(f"estimates: {len(common)} in both, {only} in only one")
    print(f"max BPM difference: {bpm_diff:.3f} (limit {BPM_TOL})")
    print(f"max quality difference: {q_diff:.1e} (limit {QUALITY_TOL:.0e})")
    print(f"board BPM: first {b[0, 2]:.1f}, last {b[-1, 2]:.1f}, "
          f"range {b[:, 2].min():.1f}-{b[:, 2].max():.1f}")
    print(f"estimate time on the board: median {np.median(us) / 1000:.0f} ms, "
          f"max {us.max() / 1000:.0f} ms")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
