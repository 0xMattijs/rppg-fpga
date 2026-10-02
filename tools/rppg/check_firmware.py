"""Check firmware/src/dsp/rppg.c against pos.py on synthetic sessions.

Builds the host harness in firmware/test/, runs both implementations on the
last WINDOW_SAMPLES frames of each session, and compares BPM, quality, and the
band-passed pulse signal.

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

BPM_TOL = 0.01        # same FFT bin
QUALITY_TOL = 1e-3
PULSE_TOL = 1e-3      # relative to the pulse's peak amplitude


def config():
    defs = dict(re.findall(r"#define\s+(\w+)\s+([\d.]+)f?", CONFIG.read_text()))
    return float(defs["FRAME_RATE_HZ"]), int(defs["WINDOW_SAMPLES"]), int(defs["FFT_SIZE"])


def run_c(csv):
    out = subprocess.run([TEST_DIR / "host_rppg", csv, "--pulse"],
                         check=True, capture_output=True, text=True).stdout.split("\n")
    _, bpm, q = out[0].split()
    return float(bpm), float(q), np.array([float(v) for v in out[1:] if v])


def run_py(csv, fs, n, nfft):
    rgb = pos.load(csv)[-n:]
    pulse = pos.bandpass(pos.pos(rgb, fs), fs)
    bpm, q, _, _ = pos.estimate_bpm(pulse, fs, nfft=nfft)
    return bpm, q, pulse


def synth(path, bpm, seconds, fs):
    subprocess.run([sys.executable, "-m", "rppg.synth", str(path), "--bpm", str(bpm),
                    "--seconds", str(seconds), "--fs", str(fs)],
                   check=True, cwd=ROOT / "tools")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", nargs="*")
    args = p.parse_args()

    fs, n, nfft = config()
    subprocess.run(["make", "-s", "-C", TEST_DIR], check=True)

    with tempfile.TemporaryDirectory() as tmp:
        cases = [Path(c) for c in args.csv]
        if not cases:
            for bpm in (45, 60, 72, 84, 100, 130, 180, 230):
                cases.append(Path(tmp) / f"synth_{bpm}.csv")
                synth(cases[-1], bpm, 20, fs)

        failed = 0
        print(f"{'session':<20} {'C bpm':>7} {'py bpm':>7} {'C q':>7} {'py q':>7} {'pulse err':>10}")
        for csv in cases:
            cb, cq, cp = run_c(csv)
            pb, pq, pp = run_py(csv, fs, n, nfft)
            err = np.max(np.abs(cp - pp)) / np.max(np.abs(pp))
            ok = abs(cb - pb) <= BPM_TOL and abs(cq - pq) <= QUALITY_TOL and err <= PULSE_TOL
            failed += not ok
            print(f"{csv.name:<20} {cb:7.2f} {pb:7.2f} {cq:7.4f} {pq:7.4f} {err:10.2e}"
                  f"  {'ok' if ok else 'FAIL'}")

    print("PASS" if not failed else f"FAIL ({failed} of {len(cases)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
