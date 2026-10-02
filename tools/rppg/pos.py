"""Offline BPM estimate with the POS algorithm (Wang et al., 2017).

Reference implementation for firmware/src/dsp/rppg.c.
"""
import argparse
import sys

import numpy as np
from scipy.signal import butter, filtfilt

HR_BAND = (0.7, 4.0)
MAX_GAP_FILL = 5        # frames; a longer gap restarts the window
HARMONIC_RATIO = 0.25     # see HARMONIC_RATIO in firmware/include/config.h


def load(path):
    """Return (frame, rgb): frame counters and (N, 3) mean RGB. Frames with no
    pixels are left out, as the firmware does."""
    d = np.genfromtxt(path, delimiter=",", names=True)
    d = d[d["pixel_count"] > 0]
    n = d["pixel_count"]
    rgb = np.stack([d["sum_r"] / n, d["sum_g"] / n, d["sum_b"] / n], axis=1)
    return d["frame"].astype(np.int64), rgb


def fill_gaps(frame, rgb, max_fill=MAX_GAP_FILL):
    """Fill frame-counter gaps of up to max_fill frames by linear interpolation.

    Yields (frame, samples, restart) once per input frame: `samples` is the
    list it contributes, interpolated ones first, and `restart` is True after
    a longer gap. Mirrors rppg_push() in the firmware.
    """
    last_f, last_x = None, None
    for f, x in zip(frame, rgb):
        filled, restart = [], False
        if last_f is not None:
            gap = (int(f) - int(last_f) - 1) % 2 ** 32
            if gap > max_fill:
                restart = True
            else:
                filled = [last_x + (k / (gap + 1)) * (x - last_x) for k in range(1, gap + 1)]
        yield f, filled + [x], restart
        last_f, last_x = f, x


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


def estimate_bpm(x, fs, nfft=512, band=HR_BAND, harmonic_ratio=HARMONIC_RATIO):
    nfft = max(nfft, len(x))
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / fs)
    idx = np.flatnonzero((f >= band[0]) & (f <= band[1]))
    k = idx[np.argmax(spec[idx])]

    # A pulse with a strong second harmonic can peak at twice the heart rate.
    # If there is a peak near half the frequency with enough power, take it.
    half = np.arange(max(k // 2 - 1, idx[0]), (k + 1) // 2 + 2)
    if len(half):
        kh = half[np.argmax(spec[half])]
        if spec[kh] >= harmonic_ratio * spec[k]:
            k = kh
    quality = spec[k] / spec[idx].sum()

    # Parabolic interpolation on power across the peak bin and its neighbors.
    # The half-frequency bin need not be a local maximum, and then the
    # parabola's vertex can land bins away: keep it within half a bin.
    a, b, c = spec[k - 1], spec[k], spec[k + 1]
    den = a - 2 * b + c
    delta = 0.5 * (a - c) / den if den < 0 else 0.0
    delta = min(max(delta, -0.5), 0.5)
    return (k + delta) * fs / nfft * 60, quality, f, spec


def windows(frame, rgb, n=300, step=30, max_fill=MAX_GAP_FILL):
    """Yield (frame, window) whenever the firmware would estimate: the window
    holds `n` samples and `step` have arrived since the last estimate.
    Gaps are filled or restart the window as in fill_gaps."""
    buf, pending = [], 0
    for f, samples, restart in fill_gaps(frame, rgb, max_fill):
        if restart:
            buf, pending = [], 0
            yield None, None            # tells track() to reset its smoothing
        buf = (buf + samples)[-n:]
        pending += len(samples)
        if len(buf) == n and pending >= step:
            pending = 0
            yield f, np.array(buf)


def track(frame, rgb, fs, n=300, step=30, alpha=0.15, nfft=512, max_fill=MAX_GAP_FILL,
          harmonic_ratio=HARMONIC_RATIO, gate=0.08):
    """Estimate BPM over time, as the firmware does.

    Returns rows of (frame, raw_bpm, smoothed_bpm, quality). Smoothing is an
    exponential moving average seeded with the first estimate after a restart;
    after that, only estimates with quality >= gate move it.
    """
    rows, smooth = [], None
    for f, w in windows(frame, rgb, n, step, max_fill):
        if w is None:
            smooth = None
            continue
        pulse = bandpass(pos(w, fs), fs)
        bpm, q, _, _ = estimate_bpm(pulse, fs, nfft, harmonic_ratio=harmonic_ratio)
        if smooth is None:
            smooth = bpm
        elif q >= gate:
            smooth += alpha * (bpm - smooth)
        rows.append((f, bpm, smooth, q))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv")
    p.add_argument("--fs", type=float, default=30.0)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    frame, rgb = load(args.csv)
    parts = list(fill_gaps(frame, rgb))
    if any(restart for _, _, restart in parts):
        print(f"warning: gaps over {MAX_GAP_FILL} frames; result spans them", file=sys.stderr)
    rgb = np.array([x for _, samples, _ in parts for x in samples])
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
