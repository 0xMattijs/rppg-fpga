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
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import pos
from .gen_coeffs import config_band, config_defines

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "firmware/test"

BPM_TOL = 0.01
QUALITY_TOL = 1e-3
PULSE_TOL = 1e-3      # relative to the pulse's peak amplitude


def config():
    defs = config_defines()
    if config_band(defs) != pos.HR_BAND:
        sys.exit(f"HR band differs: config.h {config_band(defs)}, pos.py {pos.HR_BAND}")
    return dict(fs=float(defs["FRAME_RATE_HZ"]), n=int(defs["WINDOW_SAMPLES"]),
                nfft=int(defs["FFT_SIZE"]), step=int(defs["ESTIMATE_EVERY"]),
                alpha=float(defs["BPM_SMOOTH_ALPHA"]), max_fill=int(defs["MAX_GAP_FILL"]),
                harmonic_ratio=float(defs["HARMONIC_RATIO"]),
                gate=float(defs["BPM_GATE_QUALITY"]))


def run_c(csv):
    lines = subprocess.run([TEST_DIR / "host_rppg", csv, "--pulse"],
                           check=True, capture_output=True, text=True).stdout.splitlines()
    rows = [tuple(float(v) for v in l.split()[1:]) for l in lines if l.startswith("EST ")]
    pulse = np.array([float(l) for l in lines if l and not l.startswith("EST ")])
    return np.array(rows), pulse


def track(frame, rgb, cfg):
    return pos.track(frame, rgb, cfg["fs"], cfg["n"], cfg["step"], cfg["alpha"], cfg["nfft"],
                     cfg["max_fill"], cfg["harmonic_ratio"], cfg["gate"])


def run_py(csv, cfg):
    frame, rgb = pos.load(csv)
    rows = track(frame, rgb, cfg)
    *_, (_, last) = (w for w in pos.windows(frame, rgb, cfg["n"], cfg["step"], cfg["max_fill"])
                     if w[1] is not None)
    pulse = pos.bandpass(pos.pos(last, cfg["fs"]), cfg["fs"])
    return np.array(rows), pulse


def synth(path, bpm, seconds, fs, extra=()):
    subprocess.run([sys.executable, "-m", "rppg.synth", str(path), "--bpm", str(bpm),
                    "--seconds", str(seconds), "--fs", str(fs), *extra],
                   check=True, cwd=ROOT / "tools")


def cut(path, start, length):
    """Delete `length` frames from a session CSV, leaving one long gap."""
    lines = Path(path).read_text().splitlines(keepends=True)
    del lines[1 + start:1 + start + length]
    Path(path).write_text("".join(lines))


# Sessions that exercise gap filling, restarts, and the harmonic check:
# name -> (bpm, synth options, frames to cut as (start, length) or None).
EXTRA_CASES = {"drop_5pct": (72, ["--drop", "0.05"], None),
               "gap_restart": (90, [], (600, 30)),
               "harmonic": (60, ["--harmonics", "1.2"], None),
               "realistic": (84, ["--realistic"], None)}


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
            for name, (bpm, extra, gap) in EXTRA_CASES.items():
                cases.append((Path(tmp) / f"{name}.csv", bpm))
                synth(cases[-1][0], bpm, 60, cfg["fs"], extra)
                if gap:
                    cut(cases[-1][0], *gap)

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
