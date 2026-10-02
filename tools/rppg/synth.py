"""Write a synthetic session CSV with a known pulse, to test pos.py without hardware.

By default the pulse is a clean sine with white noise. Options add the effects
a real recording has, one at a time or all together with --realistic:

  --drift      slow change in light level (fraction of full scale)
  --flicker    light flicker at this frequency in Hz, aliased by the frame rate
  --motion     head movements per minute: shading, specular, and background
               pixels entering the fixed ROI
  --hrv        heart-rate variation in bpm (breathing and slow drift)
  --harmonics  PPG wave shape: weight of the 2nd harmonic
  --jitter     frame timing jitter in ms (standard deviation)
  --drop       fraction of frames lost (gaps in the frame counter)
"""
import argparse

import numpy as np

BASE = np.array([150.0, 110.0, 90.0])          # mean skin color
BACKGROUND = np.array([70.0, 80.0, 95.0])      # wall and hair at the ROI edge
PULSE = np.array([0.3, 1.0, 0.15]) * 0.4       # pulse amplitude; strongest in green
PIXELS = 40000

REALISTIC = dict(drift=0.1, flicker=100.0, flicker_amp=0.005, motion=3.0, hrv=4.0,
                 harmonics=0.4, jitter=2.0, drop=0.005)


def generate(bpm=72.0, seconds=30.0, fs=30.0, seed=0, noise=0.2, drift=0.0, flicker=0.0,
             flicker_amp=0.005, motion=0.0, hrv=0.0, harmonics=0.0, jitter=0.0, drop=0.0):
    """Return (frame, t, rgb, true_bpm): frame counter, capture time in s,
    (N, 3) mean RGB, and the instantaneous heart rate at each frame."""
    rng = np.random.default_rng(seed)
    frame = np.arange(int(seconds * fs))
    t = frame / fs + rng.normal(0, jitter / 1000, len(frame))
    keep = rng.random(len(frame)) >= drop
    frame, t = frame[keep], t[keep]

    # Heart rate: breathing (~0.25 Hz) plus a slow wander, integrated to phase.
    tf = np.arange(0, seconds + 1, 1e-3)
    rate = bpm + hrv * (np.sin(2 * np.pi * 0.25 * tf + rng.uniform(0, 2 * np.pi))
                        + 0.5 * np.sin(2 * np.pi * 0.02 * tf + rng.uniform(0, 2 * np.pi)))
    phase = 2 * np.pi * np.cumsum(rate / 60) * 1e-3
    ph = np.interp(t, tf, phase)
    true_bpm = np.interp(t, tf, rate)
    pulse = np.sin(ph) + harmonics * np.sin(2 * ph - 0.6)
    pulse /= np.sqrt(1 + harmonics ** 2)

    # Light level: slow drift plus flicker sampled at the frame times.
    light = 1 + drift * (t / seconds - 0.5) + 0.3 * drift * np.sin(2 * np.pi * 0.05 * t)
    if flicker:
        light += flicker_amp * np.sin(2 * np.pi * flicker * t)

    # Head movements: shading changes on all channels, a white specular
    # component, and background pixels entering the fixed ROI. Each follows
    # its own timing within a movement, as position and angle do. POS cancels
    # one color direction per window; if all three moved together, it would
    # cancel the whole movement.
    def bump(t0, dur):
        return np.where(np.abs(t - t0) < dur / 2,
                        0.5 + 0.5 * np.cos(2 * np.pi * (t - t0) / dur), 0.0)

    shade = np.zeros(len(t))
    spec = np.zeros(len(t))
    mix = np.zeros(len(t))
    for _ in range(rng.poisson(motion * seconds / 60)):
        t0 = rng.uniform(0, seconds)
        shade += rng.uniform(-0.03, 0.03) * bump(t0, rng.uniform(0.5, 2.0))
        spec += rng.uniform(0, 0.02) * bump(t0 + rng.uniform(-0.4, 0.4), rng.uniform(0.3, 1.5))
        mix += rng.uniform(0, 0.05) * bump(t0 + rng.uniform(-0.4, 0.4), rng.uniform(0.5, 2.0))

    skin = BASE * (1 + np.outer(pulse, PULSE / BASE))
    face = skin + (spec * BASE.mean())[:, None]
    scene = (1 - mix)[:, None] * face + mix[:, None] * BACKGROUND
    rgb = (light * (1 + shade))[:, None] * scene
    rgb += rng.normal(0, noise, rgb.shape)
    return frame, t, rgb, true_bpm


def write_csv(path, frame, t, rgb):
    with open(path, "w") as f:
        f.write("frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count\n")
        for i, (r, g, b) in enumerate(rgb):
            f.write(f"{frame[i]},{int(t[i] * 1e6)},{int(r * PIXELS)},{int(g * PIXELS)},"
                    f"{int(b * PIXELS)},{PIXELS}\n")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out")
    p.add_argument("--bpm", type=float, default=72)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--fs", type=float, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--noise", type=float, default=0.2)
    p.add_argument("--realistic", action="store_true", help=f"all effects: {REALISTIC}")
    for k in REALISTIC:
        p.add_argument("--" + k.replace("_", "-"), type=float, default=None)
    args = p.parse_args()

    effects = {k: (REALISTIC[k] if args.realistic else 0.0) for k in REALISTIC}
    effects["flicker_amp"] = REALISTIC["flicker_amp"]
    effects.update({k: v for k in REALISTIC if (v := getattr(args, k)) is not None})
    frame, t, rgb, _ = generate(args.bpm, args.seconds, args.fs, args.seed, args.noise,
                                **effects)
    write_csv(args.out, frame, t, rgb)


if __name__ == "__main__":
    main()
