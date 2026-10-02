"""Offline BPM estimate with the POS algorithm (Wang et al., 2017).

Reference implementation for firmware/src/dsp/rppg.c.
"""
import argparse

import numpy as np
from scipy.signal import butter, filtfilt

HR_BAND = (0.7, 4.0)


def load(path):
    d = np.genfromtxt(path, delimiter=",", names=True)
    n = np.maximum(d["pixel_count"], 1)
    rgb = np.stack([d["sum_r"] / n, d["sum_g"] / n, d["sum_b"] / n], axis=1)
    return rgb


def pos(rgb, fs, win_s=1.6):
    """Return the POS pulse signal for an (N, 3) array of mean RGB values."""
    n = len(rgb)
    w = int(win_s * fs)
    h = np.zeros(n)
    proj = np.array([[0, 1, -1], [-2, 1, 1]])
    for t in range(n - w + 1):
        c = rgb[t:t + w]
        cn = c / c.mean(axis=0)
        s = cn @ proj.T
        p = s[:, 0] + (s[:, 0].std() / (s[:, 1].std() + 1e-9)) * s[:, 1]
        h[t:t + w] += p - p.mean()
    return h


def bandpass(x, fs, band=HR_BAND, order=3):
    b, a = butter(order, [band[0] / (fs / 2), band[1] / (fs / 2)], btype="band")
    return filtfilt(b, a, x)


def estimate_bpm(x, fs, nfft=512, band=HR_BAND):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=max(nfft, len(x)))) ** 2
    f = np.fft.rfftfreq(max(nfft, len(x)), 1 / fs)
    m = (f >= band[0]) & (f <= band[1])
    k = np.argmax(spec[m])
    quality = spec[m][k] / spec[m].sum()
    return f[m][k] * 60, quality, f, spec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv")
    p.add_argument("--fs", type=float, default=30.0)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    rgb = load(args.csv)
    pulse = bandpass(pos(rgb, args.fs), args.fs)
    bpm, q, f, spec = estimate_bpm(pulse, args.fs)
    print(f"BPM {bpm:.1f}  quality {q:.2f}")

    if args.plot:
        import matplotlib.pyplot as plt
        _, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6))
        a1.plot(np.arange(len(pulse)) / args.fs, pulse)
        a1.set_xlabel("time (s)")
        a2.plot(f * 60, spec)
        a2.set_xlim(30, 250)
        a2.set_xlabel("bpm")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
