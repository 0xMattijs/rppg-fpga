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
    # All windows at once: c[t] is rgb[t:t + w], shape (windows, 3, w).
    c = np.lib.stride_tricks.sliding_window_view(rgb, w, axis=0)
    cn = c / c.mean(axis=2, keepdims=True)
    s = np.einsum("ij,tjw->tiw", proj, cn)
    alpha = s[:, 0].std(axis=1) / (s[:, 1].std(axis=1) + 1e-9)
    p = s[:, 0] + alpha[:, None] * s[:, 1]
    p -= p.mean(axis=1, keepdims=True)
    for k in range(w):                      # overlap-add
        h[k:k + len(p)] += p[:, k]
    return h


def bandpass(x, fs, band=HR_BAND, order=3):
    b, a = butter(order, [band[0] / (fs / 2), band[1] / (fs / 2)], btype="band")
    return filtfilt(b, a, x)


def estimate_bpm(x, fs, nfft=512, band=HR_BAND):
    nfft = max(nfft, len(x))
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / fs)
    idx = np.flatnonzero((f >= band[0]) & (f <= band[1]))
    k = idx[np.argmax(spec[idx])]
    quality = spec[k] / spec[idx].sum()

    # Parabolic interpolation on power across the peak bin and its neighbors.
    a, b, c = spec[k - 1], spec[k], spec[k + 1]
    den = a - 2 * b + c
    delta = 0.5 * (a - c) / den if den < 0 else 0.0
    return (k + delta) * fs / nfft * 60, quality, f, spec


def track(rgb, fs, n=300, step=30, alpha=0.3, nfft=512):
    """Estimate every `step` frames over the last `n` frames, as the firmware does.

    Returns rows of (frame, raw_bpm, smoothed_bpm, quality). Smoothing is an
    exponential moving average seeded with the first estimate.
    """
    rows, smooth = [], None
    for end in range(n, len(rgb) + 1, step):
        pulse = bandpass(pos(rgb[end - n:end], fs), fs)
        bpm, q, _, _ = estimate_bpm(pulse, fs, nfft)
        smooth = bpm if smooth is None else smooth + alpha * (bpm - smooth)
        rows.append((end - 1, bpm, smooth, q))
    return rows


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
