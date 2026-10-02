"""Write a synthetic session CSV with a known pulse, to test pos.py without hardware."""
import argparse

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out")
    p.add_argument("--bpm", type=float, default=72)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--fs", type=float, default=30)
    args = p.parse_args()

    rng = np.random.default_rng(0)
    t = np.arange(int(args.seconds * args.fs)) / args.fs
    pulse = np.sin(2 * np.pi * args.bpm / 60 * t)
    base = np.array([150.0, 110.0, 90.0])
    amp = np.array([0.3, 1.0, 0.15]) * 0.4       # strongest in green
    rgb = base + np.outer(pulse, amp) + rng.normal(0, 0.2, (len(t), 3))
    n = 40000
    with open(args.out, "w") as f:
        f.write("frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count\n")
        for i, (r, g, b) in enumerate(rgb):
            f.write(f"{i},{int(t[i] * 1e6)},{int(r * n)},{int(g * n)},{int(b * n)},{n}\n")


if __name__ == "__main__":
    main()
