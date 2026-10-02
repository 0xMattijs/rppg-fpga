"""Compare camera BPM with the M5 reference: MAE and a Bland-Altman plot (Phase 5)."""
import argparse

import numpy as np


def load(path):
    rows = [l.strip().split(",") for l in open(path) if l.startswith("BPM,")]
    a = np.array([[float(v) for v in r[1:5]] for r in rows])
    return a[:, 1], a[:, 2]  # camera, m5


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log")
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    cam, ref = load(args.log)
    diff = cam - ref
    mae = np.abs(diff).mean()
    bias, sd = diff.mean(), diff.std()
    print(f"n={len(diff)}  MAE {mae:.2f} bpm  bias {bias:+.2f}  LoA ±{1.96 * sd:.2f}")
    print("PASS" if mae < 5 else "FAIL", "(target MAE < 5 bpm)")

    if args.plot:
        import matplotlib.pyplot as plt
        mean = (cam + ref) / 2
        plt.scatter(mean, diff, s=8)
        for y in (bias, bias + 1.96 * sd, bias - 1.96 * sd):
            plt.axhline(y, ls="--", c="gray")
        plt.xlabel("mean of camera and M5 (bpm)")
        plt.ylabel("camera − M5 (bpm)")
        plt.title("Bland–Altman")
        plt.show()


if __name__ == "__main__":
    main()
