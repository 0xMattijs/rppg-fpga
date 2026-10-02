"""Score pos.py against the true BPM on synthetic sessions with real-world effects.

Runs pos.track the way the firmware does (an estimate every ESTIMATE_EVERY
frames over the last WINDOW_SAMPLES), for each effect alone at 1x, 3x, and 10x
its realistic level in synth.REALISTIC, and for all effects together. Each
estimate is compared with the true heart rate averaged over its window.
firmware/src/dsp/rppg.c matches pos.py (see check_firmware.py), so the scores
hold for the firmware too.

The 10x column is past realistic on purpose: it shows how much margin each
effect has, not how the monitor behaves in a normal room.

    python -m rppg.stress
    python -m rppg.stress --seeds 10 --bpm 60 90
"""
import argparse

import numpy as np

from . import pos, synth
from .check_firmware import config, track

SCALES = (1, 3, 10)
TARGET_MAE = 5.0

# Effect name -> the synth.generate argument that scales.
EFFECTS = {"drift": "drift", "flicker 100 Hz": "flicker_amp", "motion": "motion",
           "hrv": "hrv", "harmonics": "harmonics", "jitter": "jitter", "drop": "drop",
           "noise": "noise"}
DEFAULT_NOISE = 0.2


def effect_args(name, scale):
    arg = EFFECTS[name]
    if arg == "noise":
        return {"noise": DEFAULT_NOISE * scale}
    if arg == "flicker_amp":
        return {"flicker": synth.REALISTIC["flicker"],
                "flicker_amp": synth.REALISTIC["flicker_amp"] * scale}
    return {arg: synth.REALISTIC[arg] * scale}


def score(effects, bpms, seeds, seconds, cfg):
    """Mean absolute error of the displayed (smoothed) BPM, and its worst case."""
    err = []
    for bpm in bpms:
        for seed in range(seeds):
            frame, _, rgb, true = synth.generate(bpm, seconds, cfg["fs"], seed, **effects)
            for f, _, shown, _ in track(frame, rgb, cfg):
                # True rate over the window: the last n frame-counter values.
                in_win = (frame > f - cfg["n"]) & (frame <= f)
                err.append(shown - true[in_win].mean())
    err = np.abs(err)
    return err.mean(), err.max()


def cell(mae, worst):
    mark = "!" if mae >= TARGET_MAE else " "
    return f"{mae:6.2f} ({worst:5.1f}){mark}"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bpm", type=float, nargs="+", default=[50, 72, 100, 140])
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--seconds", type=float, default=45)
    args = p.parse_args()

    cfg = config()
    run = lambda effects: score(effects, args.bpm, args.seeds, args.seconds, cfg)
    print(f"{len(args.bpm)} rates x {args.seeds} seeds x {args.seconds:g} s. "
          f"MAE of the displayed BPM (worst case), in bpm. ! = over the "
          f"{TARGET_MAE:g} bpm target.\n")
    print(f"{'effect':<16} {'1x level':>9}" + "".join(f"{f'{s}x':>16}" for s in SCALES))
    print(f"{'clean':<16} {'':>9} {cell(*run({}))}")
    for name, arg in EFFECTS.items():
        level = DEFAULT_NOISE if arg == "noise" else synth.REALISTIC[arg]
        cells = " ".join(cell(*run(effect_args(name, s))) for s in SCALES)
        print(f"{name:<16} {level:9g} {cells}")
    print(f"{'all, realistic':<16} {'':>9} {cell(*run(dict(synth.REALISTIC)))}")


if __name__ == "__main__":
    main()
