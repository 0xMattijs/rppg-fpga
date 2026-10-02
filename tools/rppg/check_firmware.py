"""Check firmware/src/dsp/rppg.c against pos.py on synthetic sessions.

Builds the host harness in firmware/test/, runs both implementations over each
session the way the firmware does (an estimate every ESTIMATE_EVERY frames over
the last WINDOW_SAMPLES), and compares every estimate's raw BPM, smoothed BPM,
and quality, plus the band-passed pulse of the last window. For synthetic
sessions it also reports the error against the true BPM.

    python -m rppg.check_firmware            # synthetic sweep
    python -m rppg.check_firmware a.csv ...  # your own recordings
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import pos

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "firmware/test"
CONFIG = ROOT / "firmware/include/config.h"

BPM_TOL = 0.01
QUALITY_TOL = 1e-3
PULSE_TOL = 1e-3      # relative to the pulse's peak amplitude


def config():
    defs = dict(re.findall(r"#define\s+(\w+)\s+([\d.]+)f?", CONFIG.read_text()))
    return dict(fs=float(defs["FRAME_RATE_HZ"]), n=int(defs["WINDOW_SAMPLES"]),
                nfft=int(defs["FFT_SIZE"]), step=int(defs["ESTIMATE_EVERY"]),
                alpha=float(defs["BPM_SMOOTH_ALPHA"]))


def run_c(csv):
    lines = subprocess.run([TEST_DIR / "host_rppg", csv, "--pulse"],
                           check=True, capture_output=True, text=True).stdout.splitlines()
    rows = [tuple(float(v) for v in l.split()[1:]) for l in lines if l.startswith("EST ")]
    pulse = np.array([float(l) for l in lines if l and not l.startswith("EST ")])
    return np.array(rows), pulse


def run_py(csv, cfg):
    rgb = pos.load(csv)
    rows = pos.track(rgb, cfg["fs"], cfg["n"], cfg["step"], cfg["alpha"], cfg["nfft"])
    last = rows[-1][0] + 1
    pulse = pos.bandpass(pos.pos(rgb[last - cfg["n"]:last], cfg["fs"]), cfg["fs"])
    return np.array(rows), pulse


def synth(path, bpm, seconds, fs):
    subprocess.run([sys.executable, "-m", "rppg.synth", str(path), "--bpm", str(bpm),
                    "--seconds", str(seconds), "--fs", str(fs)],
                   check=True, cwd=ROOT / "tools")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", nargs="*")
    args = p.parse_args()

    cfg = config()
    subprocess.run(["make", "-s", "-C", TEST_DIR], check=True)

    with tempfile.TemporaryDirectory() as tmp:
        cases = [(Path(c), None) for c in args.csv]
        if not cases:
            for bpm in (45, 60, 72, 84, 100, 130, 180, 230):
                cases.append((Path(tmp) / f"synth_{bpm}.csv", bpm))
                synth(cases[-1][0], bpm, 30, cfg["fs"])

        failed = 0
        print(f"{'session':<16} {'est':>3} {'C bpm':>7} {'py bpm':>7} {'max diff':>9} "
              f"{'q diff':>8} {'pulse err':>9} {'vs true':>7}")
        for csv, true_bpm in cases:
            c, cp = run_c(csv)
            py, pp = run_py(csv, cfg)
            if c.shape != py.shape or not np.array_equal(c[:, 0], py[:, 0]):
                print(f"{csv.name:<16} estimate frames differ: C {c[:, 0]}, py {py[:, 0]}  FAIL")
                failed += 1
                continue
            bpm_diff = np.max(np.abs(c[:, 1:3] - py[:, 1:3]))
            q_diff = np.max(np.abs(c[:, 3] - py[:, 3]))
            err = np.max(np.abs(cp - pp)) / np.max(np.abs(pp))
            ok = bpm_diff <= BPM_TOL and q_diff <= QUALITY_TOL and err <= PULSE_TOL
            failed += not ok
            vs_true = f"{c[-1, 2] - true_bpm:+7.2f}" if true_bpm else f"{'':>7}"
            print(f"{csv.name:<16} {len(c):3d} {c[-1, 2]:7.2f} {py[-1, 2]:7.2f} {bpm_diff:9.1e} "
                  f"{q_diff:8.1e} {err:9.1e} {vs_true}  {'ok' if ok else 'FAIL'}")

    print("PASS" if not failed else f"FAIL ({failed} of {len(cases)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
