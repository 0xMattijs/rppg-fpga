"""Check a capture and plot the raw ROI signal (Phase 2).

Prints the frame rate from the fabric timestamps, dropped frames, and the
strongest frequency in the band-passed green channel. With --plot, shows the
mean R, G, and B, the band-passed green channel, and its spectrum.

The timestamps come from the FPGA's RC oscillator, which can be off by a
percent or so; --fs overrides the measured rate.
"""
import argparse

import numpy as np

from .pos import HR_BAND, bandpass


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("csv")
    p.add_argument("--fs", type=float, help="frame rate in Hz (default: from timestamps)")
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    d = np.genfromtxt(args.csv, delimiter=",", names=True)
    d = d[d["pixel_count"] > 0]
    frame = d["frame"].astype(np.int64)
    t_us = d["timestamp_us"].astype(np.int64)
    n = d["pixel_count"]
    rgb = np.stack([d["sum_r"] / n, d["sum_g"] / n, d["sum_b"] / n], axis=1)

    df = np.diff(frame)
    dropped = int((df - 1).clip(min=0).sum())
    dt = np.diff(t_us) % 2 ** 32 / df
    fs = args.fs or 1e6 / np.median(dt)
    print(f"{len(frame)} frames, {dropped} dropped, {len(frame) / fs:.1f} s")
    print(f"frame rate {1e6 / np.median(dt):.3f} Hz from timestamps "
          f"(period jitter {dt.std():.0f} us); using {fs:.3f} Hz")
    print(f"ROI: {int(n[0])} pixels, mean RGB {rgb.mean(axis=0).round(1)} of 255")

    # Index by frame counter, so dropped frames don't shift the time axis.
    t = (frame - frame[0]) / fs
    t_even = np.arange(0, t[-1], 1 / fs)
    g = np.interp(t_even, t, rgb[:, 1])
    g_bp = bandpass(g / g.mean() - 1, fs)

    nfft = max(4096, 1 << int(np.ceil(np.log2(len(g_bp)))))
    spec = np.abs(np.fft.rfft(g_bp * np.hanning(len(g_bp)), nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / fs)
    band = (f >= HR_BAND[0]) & (f <= HR_BAND[1])
    peak = f[band][np.argmax(spec[band])]
    print(f"green peak at {peak:.2f} Hz = {peak * 60:.0f} bpm")

    if args.plot:
        import matplotlib.pyplot as plt
        _, ax = plt.subplots(3, 1, figsize=(10, 8))
        for i, c in enumerate("rgb"):
            ax[0].plot(t, rgb[:, i] - rgb[:, i].mean(), c, lw=0.8, label=f"{c} - mean")
        ax[0].set_ylabel("mean level")
        ax[0].legend(loc="upper right")
        ax[1].plot(t_even, g_bp * 100, "g")
        ax[1].set_ylabel(f"green, {HR_BAND[0]}-{HR_BAND[1]} Hz (%)")
        ax[1].set_xlabel("time (s)")
        ax[2].plot(f[band] * 60, spec[band], "g")
        ax[2].axvline(peak * 60, color="k", ls=":")
        ax[2].set_xlabel("bpm")
        ax[2].set_ylabel("power")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
