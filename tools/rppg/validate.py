"""Compare the board's BPM with a reference heart rate: MAE and Bland-Altman (Phase 5).

The reference is a watch's heart rate, matched by clock time to the board's
estimates in one or more .est files from capture.py:

    python -m rppg.validate ../data/still.est --watch export.zip --plot still.png

--watch takes an Apple Health export (export.zip, or the .xml inside it) or
a CSV of time,bpm rows, with the time in Unix seconds or ISO 8601 with a time
zone. An Apple Watch records heart rate about every 5 s during a Workout.

Each estimate covers the 10 s before its time stamp, so by default it is
compared with the watch at the middle of that window (--lag 5). The watch
value is interpolated between samples at most --max-gap seconds apart;
estimates outside the watch's coverage are left out.
"""
import argparse
import csv
import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

HR_TYPE = "HKQuantityTypeIdentifierHeartRate"


def load_est(paths):
    """Return (t, bpm, quality) from capture.py's .est files, sorted by t."""
    rows = []
    for path in paths:
        for line in open(path):
            f = line.split()
            if len(f) != 7:
                sys.exit(f"{path}: no clock time on the EST lines; record it "
                         "again with the current capture.py")
            rows.append((float(f[6]), float(f[3]), float(f[4])))
    a = np.array(sorted(rows)).reshape(-1, 3)
    return a[:, 0], a[:, 1], a[:, 2]


def parse_time(s):
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    # Apple Health: "2026-10-02 18:50:01 +0200"
    for fmt in ("%Y-%m-%d %H:%M:%S %z", None):
        try:
            d = datetime.strptime(s, fmt) if fmt else datetime.fromisoformat(s)
        except ValueError:
            continue
        if d.tzinfo is None:
            sys.exit(f"time without a time zone: {s!r}")
        return d.timestamp()
    sys.exit(f"can't read the time {s!r}")


def health_xml(path):
    """Open the export's main XML, inside a zip or on its own. The file's
    name depends on the phone's language, so take the largest .xml that
    isn't the clinical-records one."""
    if not zipfile.is_zipfile(path):
        return open(path, "rb")
    z = zipfile.ZipFile(path)
    xmls = [i for i in z.infolist()
            if i.filename.endswith(".xml") and "cda" not in i.filename.lower()]
    if not xmls:
        sys.exit(f"{path}: no Health export XML inside")
    return z.open(max(xmls, key=lambda i: i.file_size))


def load_health(path, t0, t1):
    """Heart-rate records between t0 and t1 from an Apple Health export."""
    out = []
    with health_xml(path) as f:
        for _, el in ElementTree.iterparse(f):
            if el.tag == "Record" and el.get("type") == HR_TYPE:
                t = parse_time(el.get("startDate"))
                if t0 <= t <= t1:
                    out.append((t, float(el.get("value"))))
            if el.tag in ("Record", "Workout", "ActivitySummary", "Correlation"):
                el.clear()
    return out


def load_csv(path, t0, t1):
    out = []
    for row in csv.reader(open(path)):
        if len(row) < 2:
            continue
        try:
            bpm = float(row[1])
        except ValueError:
            continue               # header
        t = parse_time(row[0])
        if t0 <= t <= t1:
            out.append((t, bpm))
    return out


def load_watch(path, t0, t1):
    path = Path(path)
    rows = (load_csv(path, t0, t1) if path.suffix.lower() == ".csv"
            else load_health(path, t0, t1))
    if not rows:
        sys.exit(f"{path}: no heart rate between "
                 f"{datetime.fromtimestamp(t0):%Y-%m-%d %H:%M:%S} and "
                 f"{datetime.fromtimestamp(t1):%H:%M:%S}")
    a = np.array(sorted(set(rows)))
    return a[:, 0], a[:, 1]


def match(t, wt, wbpm, max_gap):
    """Watch heart rate at times t, interpolated; NaN where the nearest
    samples on either side are more than max_gap apart."""
    i = np.searchsorted(wt, t)
    ok = (i > 0) & (i < len(wt))
    lo, hi = np.clip(i - 1, 0, len(wt) - 1), np.clip(i, 0, len(wt) - 1)
    ok &= (wt[hi] - wt[lo]) <= max_gap
    ref = np.interp(t, wt, wbpm)
    ref[~ok] = np.nan
    # An exact hit on a sample is fine whatever the gaps around it.
    exact = np.isin(t, wt)
    ref[exact] = np.interp(t[exact], wt, wbpm)
    return ref


def stats(cam, ref):
    d = cam - ref
    return len(d), np.abs(d).mean(), d.mean(), 1.96 * d.std()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("est", nargs="+", help=".est files from capture.py")
    p.add_argument("--watch", required=True,
                   help="Apple Health export.zip or .xml, or a time,bpm CSV")
    p.add_argument("--lag", type=float, default=5.0,
                   help="seconds the watch is read before each estimate (default 5)")
    p.add_argument("--max-gap", type=float, default=15.0,
                   help="longest gap between watch samples to interpolate over (s)")
    p.add_argument("--min-quality", type=float, default=0.08,
                   help="also report estimates at or above this quality "
                        "(default: QUALITY_LOW in config.h)")
    p.add_argument("--plot", help="save the plots to this image file")
    args = p.parse_args()

    t, cam, q = load_est(args.est)
    wt, wbpm = load_watch(args.watch, t[0] - args.lag - 60, t[-1] + 60)
    ref = match(t - args.lag, wt, wbpm, args.max_gap)
    have = ~np.isnan(ref)
    print(f"{len(t)} estimates, {len(wt)} watch samples "
          f"({wbpm.min():.0f}-{wbpm.max():.0f} bpm), {have.sum()} matched")
    if not have.any():
        sys.exit("no estimate falls inside the watch's coverage")

    good = have & (q >= args.min_quality)
    for name, sel in (("all", have), (f"quality >= {args.min_quality}", good)):
        if sel.any():
            n, mae, bias, loa = stats(cam[sel], ref[sel])
            print(f"{name:>16}: n={n:4d}  MAE {mae:5.2f} bpm  bias {bias:+6.2f}"
                  f"  limits of agreement ±{loa:.2f}")

    # How the error changes with the lag, to check the default.
    lags = np.arange(0, 16)
    maes = []
    for lag in lags:
        r = match(t - lag, wt, wbpm, args.max_gap)
        s = ~np.isnan(r)
        maes.append(np.abs(cam[s] - r[s]).mean() if s.any() else np.nan)
    best = lags[np.nanargmin(maes)]
    print(f"MAE by lag: best at {best} s ({np.nanmin(maes):.2f} bpm); "
          + " ".join(f"{l}:{m:.1f}" for l, m in zip(lags, maes)))

    _, mae, _, _ = stats(cam[have], ref[have])
    print("PASS" if mae < 5 else "FAIL", "(target MAE < 5 bpm, all matched estimates)")

    if args.plot:
        plot(args.plot, t, cam, q, wt, wbpm, ref, have, args)


def plot(out, t, cam, q, wt, wbpm, ref, have, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.5),
                                 gridspec_kw={"width_ratios": [2, 1]})
    t0 = t[0]
    # Break the watch's line where it has no samples.
    gap = np.flatnonzero(np.diff(wt) > args.max_gap) + 1
    a1.plot(np.insert(wt - t0, gap, np.nan), np.insert(wbpm, gap, np.nan),
            "-o", ms=3, c="tab:red", label="watch")
    low = q < args.min_quality
    a1.plot(t - t0 - args.lag, cam, c="tab:blue", lw=1, label="board")
    a1.scatter(t[low] - t0 - args.lag, cam[low], s=10, c="tab:gray", zorder=3,
               label=f"board, quality < {args.min_quality}")
    a1.set_xlim(-args.lag - 5, t[-1] - t0 + 5)
    a1.set_xlabel("time (s), board plotted at the middle of its window")
    a1.set_ylabel("heart rate (bpm)")
    a1.legend()

    c, r = cam[have], ref[have]
    d, m = c - r, (c + r) / 2
    bias, loa = d.mean(), 1.96 * d.std()
    a2.scatter(m, d, s=8, c=np.where(low[have], "tab:gray", "tab:blue"))
    for y, ls in ((bias, "-"), (bias + loa, "--"), (bias - loa, "--")):
        a2.axhline(y, ls=ls, c="gray", lw=1)
    a2.set_xlabel("mean of board and watch (bpm)")
    a2.set_ylabel("board − watch (bpm)")
    a2.set_title(f"Bland–Altman: bias {bias:+.1f}, limits ±{loa:.1f}")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"plots in {out}")


if __name__ == "__main__":
    main()
