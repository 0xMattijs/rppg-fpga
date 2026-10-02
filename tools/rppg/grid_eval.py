"""Compare the whole ROI, the skin mask, and the 4 x 4 grid on one recording (Phase 6).

    python -m rppg.grid_eval ../data/talking.csv
    python -m rppg.grid_eval ../data/talking.csv --watch ~/Downloads/export.zip

capture.py records the whole ROI's sums (the board's DSP input, every pixel)
in the CSV and the grid's skin-only cells in the .grid file next to it, from
the same frames. This script runs the firmware's estimate (rppg.pos.track:
POS, band-pass, FFT peak, gated smoothing) over three inputs:

  whole ROI  the CSV: what the board uses today (Phase 5)
  skin       all 16 cells added up: the same box, skin pixels only
  weighted   each cell on its own, then their pulses added up, each scaled
             to unit variance and weighted by its own quality (peak power /
             in-band power), so cells with a clear pulse count most

It prints each cell's skin pixels and median quality, as the camera sees
them (the LCD and the preview show the image mirrored). With --watch, it
matches every estimate to the Apple Watch as rppg.validate does, using the
PC times in the .est file.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

from . import grid, pos, validate

FS = 30.0
MIN_PIXELS = 200      # a cell needs this many skin pixels in every frame of a window


def load(csv_path):
    """(frames, whole RGB means, cell RGB means, cell counts), on the frames
    that are in both files."""
    frame, whole = pos.load(csv_path)
    gframe, cells = grid.load(Path(csv_path).with_suffix(".grid"))
    common, i, j = np.intersect1d(frame, gframe, return_indices=True)
    if len(common) == 0:
        sys.exit(f"{csv_path}: no frames in both the CSV and the .grid file")
    n = cells[j, :, 3].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = cells[j, :, :3] / n[..., None]
    return common, whole[i], means, n, cells[j]


def estimate(pulse):
    bpm, q, _, _ = pos.estimate_bpm(pulse, FS)
    return bpm, q


def cell_pulse(rgb):
    return pos.bandpass(pos.pos(rgb, FS), FS)


def run(frames, whole, means, counts, sums):
    """Estimates per method: dict name -> rows of (frame, bpm_raw, bpm, q),
    and per-cell qualities (windows x 16, NaN where a cell was left out)."""
    # Pack each frame's inputs into one vector so pos.windows fills gaps in
    # all of them at once: whole RGB, skin RGB, cell RGB, cell counts.
    skin = sums[:, :, :3].sum(axis=1) / np.maximum(sums[:, :, 3].sum(axis=1), 1)[:, None]
    packed = np.column_stack([whole, skin, np.nan_to_num(means).reshape(len(frames), -1),
                              counts])
    rows = {"whole ROI": [], "skin": [], "weighted": []}
    smooth = dict.fromkeys(rows)
    cell_q = []
    for f, w in pos.windows(frames, packed):
        if w is None:
            smooth = dict.fromkeys(rows)
            continue
        est = {"whole ROI": estimate(cell_pulse(w[:, 0:3])),
               "skin": estimate(cell_pulse(w[:, 3:6]))}

        c_rgb = w[:, 6:54].reshape(len(w), 16, 3)
        c_n = w[:, 54:70]
        combined, qs = np.zeros(len(w)), np.full(16, np.nan)
        for c in range(16):
            if c_n[:, c].min() < MIN_PIXELS:
                continue
            p = cell_pulse(c_rgb[:, c])
            _, qs[c] = estimate(p)
            combined += qs[c] * p / (p.std() + 1e-12)
        cell_q.append(qs)
        est["weighted"] = estimate(combined) if np.isfinite(qs).any() else (np.nan, 0.0)

        for name, (bpm, q) in est.items():
            if np.isnan(bpm):
                continue
            if smooth[name] is None:
                smooth[name] = bpm
            elif q >= 0.08:                          # BPM_GATE_QUALITY
                smooth[name] += 0.15 * (bpm - smooth[name])   # BPM_SMOOTH_ALPHA
            rows[name].append((f, bpm, smooth[name], q))
    return {k: np.array(v) for k, v in rows.items()}, np.array(cell_q)


def print_cells(title, values, fmt):
    print(title)
    for r in range(4):
        print("   " + " ".join(fmt(v) for v in values[4 * r:4 * r + 4]))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="\n".join(__doc__.splitlines()[2:]))
    p.add_argument("csv", type=Path)
    p.add_argument("--watch", help="Apple Health export.zip or .xml, or a time,bpm CSV")
    p.add_argument("--lag", type=float, default=5.0, help="as in rppg.validate")
    p.add_argument("--max-gap", type=float, default=15.0, help="as in rppg.validate")
    args = p.parse_args()

    frames, whole, means, counts, sums = load(args.csv)
    print(f"{len(frames)} frames with grid cells")
    print_cells("skin pixels per cell, median (camera's view, not mirrored):",
                np.median(counts, axis=0), lambda v: f"{v:6.0f}")
    whole_n = np.genfromtxt(args.csv, delimiter=",", names=True)["pixel_count"]
    print(f"skin: {np.median(counts.sum(axis=1)) / np.median(whole_n):.0%} of the ROI's pixels")

    rows, cell_q = run(frames, whole, means, counts, sums)
    if len(cell_q):
        print_cells("median quality per cell (blank: under "
                    f"{MIN_PIXELS} skin pixels):", np.nanmedian(cell_q, axis=0)
                    if np.isfinite(cell_q).any() else np.full(16, np.nan),
                    lambda v: "   -  " if np.isnan(v) else f"{v:6.3f}")

    ref = None
    if args.watch:
        # PC time of each frame, from the board's estimates in the .est file.
        est = np.loadtxt(args.csv.with_suffix(".est"), usecols=(1, 6), ndmin=2)
        if len(est) < 2:
            sys.exit("the .est file needs two estimates to time the frames")
        b, a = np.polyfit(est[:, 0], est[:, 1], 1)
        t_all = np.concatenate([r[:, 0] for r in rows.values() if len(r)]) * b + a
        wt, wbpm = validate.load_watch(args.watch, t_all.min() - args.lag - 60,
                                       t_all.max() + 60)

    print(f"\n{'':>10}  {'n':>4}  {'median q':>8}" +
          ("  {:>9}  {:>7}  {:>9}  {:>9}".format("MAE", "bias", "LoA", "MAE q>=.08")
           if args.watch else "  {:>9}".format("BPM range")))
    for name, r in rows.items():
        if not len(r):
            print(f"{name:>10}  no estimates")
            continue
        line = f"{name:>10}  {len(r):4d}  {np.median(r[:, 3]):8.3f}"
        if args.watch:
            t = r[:, 0] * b + a
            ref = validate.match(t - args.lag, wt, wbpm, args.max_gap)
            have = ~np.isnan(ref)
            if not have.any():
                line += "  no watch data"
            else:
                _, mae, bias, loa = validate.stats(r[have, 2], ref[have])
                good = have & (r[:, 3] >= 0.08)
                mae_q = (validate.stats(r[good, 2], ref[good])[1]
                         if good.any() else np.nan)
                line += f"  {mae:9.2f}  {bias:+7.2f}  {loa:9.2f}  {mae_q:9.2f}"
        else:
            line += f"  {r[:, 2].min():4.0f}-{r[:, 2].max():<4.0f}"
        print(line)


if __name__ == "__main__":
    main()
