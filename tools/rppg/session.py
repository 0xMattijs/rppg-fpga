"""Run one validation session against the Apple Watch, start to finish (Phase 5).

    python -m rppg.session talking                 # 5 minutes
    python -m rppg.session exercise --minutes 3

The steps:

1. Opens the camera preview. Check that your forehead is inside the green
   box, with the lamp on and you in the recording position.
2. C calibrates the camera to the light (like SW3) and fits the skin mask
   to your face.
3. R records for --minutes, with the preview on. Q, closing the window, or
   Ctrl+C stops early.
4. Waits for a new Health export (a .zip) in ~/Downloads, then runs
   rppg.validate and rppg.check_board on the recording.

Press the keys in the preview window, or type them in the terminal followed
by Enter. Ctrl+C while waiting for the export skips the comparison and
prints the commands to run it later.

Everything goes to data/<name>.*: .csv, .est, and .grid from capture.py, _frame.png
(the framing at the start), .png (validate's plots), and .log (the board's
messages and both reports).
"""
import argparse
import select
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from .board import LineReader, open_board, send
from .capture import Recorder, log
from .preview import Preview

TOOLS = Path(__file__).resolve().parents[1]
DATA = TOOLS.parent / "data"


def terminal_keys():
    """Keys typed in the terminal (a line each, first letter), if any."""
    keys = []
    while select.select([sys.stdin], [], [], 0)[0]:
        line = sys.stdin.readline()
        if not line:
            break
        keys.append(line.strip()[:1].lower())
    return keys


def record(args, base, logfile):
    """Steps 1 to 3. Returns True if the recording has estimates."""
    win = Preview(title=f"rPPG session: {args.name}")
    rec = None
    saved = False
    with open_board(args.port, args.baud) as ser:
        send(ser, "preview 1")
        reader = LineReader(ser)
        state = "framing"
        why = "the window was closed"
        win.set_status("Forehead in the green box? C: calibrate   Q: quit")
        log("Check the framing in the preview window, then press C to calibrate.",
            logfile)
        try:
            while win.alive():
                for line in reader.lines():
                    win.feed(line)
                    if rec:
                        rec.feed(line)
                        if win.frames and not saved:
                            win.fig.savefig(base.with_name(base.name + "_frame.png"))
                            saved = True
                    elif line.startswith("#"):
                        log(line, logfile)
                        # The skin fit follows the camera's lock.
                        if line.startswith("# skin") and state == "calibrating":
                            state = "ready"
                            win.set_status("Calibrated. R: record "
                                           f"{args.minutes:g} min   C: again   Q: quit")
                            log("Press R to start recording.", logfile)
                    if line.startswith("# error"):
                        print(line, file=sys.stderr)
                keys = win.pop_keys() + terminal_keys()
                if "q" in keys:
                    why = "Q was pressed"
                    break
                if "c" in keys and state in ("framing", "ready"):
                    state = "calibrating"
                    win.set_status("Calibrating: sit still, look at the camera")
                    send(ser, "calibrate")
                if "r" in keys and state == "ready":
                    state = "recording"
                    rec = Recorder(base.with_suffix(".csv"), logfile)
                    send(ser, "grid 1", "restart")
                    t0 = time.time()
                if state == "recording":
                    left = args.minutes * 60 - (time.time() - t0)
                    if left <= 0:
                        why = "the time was up"
                        break
                    win.set_status(f"Recording, {int(left) // 60}:{int(left) % 60:02d} "
                                   "left   Q: stop early")
                win.pump()
        except KeyboardInterrupt:
            why = "Ctrl+C was pressed"
        finally:
            send(ser, "preview 0", "grid 0")
            log(f"Stopped {state}: {why}.", logfile)
            if rec:
                rec.close()
    win.plt.close(win.fig)
    return rec is not None and rec.est_path.stat().st_size > 0


def is_health_export(path):
    if not zipfile.is_zipfile(path):
        return False
    return any(n.endswith(".xml") for n in zipfile.ZipFile(path).namelist())


def wait_for_export(downloads, since):
    """The first .zip in downloads written after since, once its size has
    stopped changing."""
    sizes = {}
    while True:
        for z in sorted(downloads.glob("*.zip")):
            st = z.stat()
            if st.st_mtime < since:
                continue
            if sizes.get(z) == st.st_size and is_health_export(z):
                return z
            sizes[z] = st.st_size
        time.sleep(2)


def report(cmd, logfile):
    """Run one of the tools and copy its output to the log."""
    log("$ python -m " + " ".join(cmd), logfile)
    r = subprocess.run([sys.executable, "-m", *cmd], cwd=TOOLS,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in r.stdout.splitlines():
        log(line, logfile)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="\n".join(__doc__.splitlines()[2:]))
    p.add_argument("name", help="session name; files go to data/<name>.*")
    p.add_argument("--minutes", type=float, default=5)
    p.add_argument("--watch", type=Path,
                   help="Health export to compare with; default: wait for a new "
                        "one in --downloads")
    p.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    p.add_argument("--force", action="store_true", help="overwrite data/<name>.*")
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    args = p.parse_args()

    base = DATA / args.name
    if base.with_suffix(".csv").exists() and not args.force:
        sys.exit(f"{base}.csv exists; pick another name or pass --force")
    DATA.mkdir(exist_ok=True)
    rel = lambda suffix: str(Path("..") / "data" / (args.name + suffix))
    validate = ["rppg.validate", rel(".est"), "--watch", None, "--plot", rel(".png")]
    check = ["rppg.check_board", rel(".csv")]

    with open(base.with_suffix(".log"), "w") as logfile:
        log(f"# session {args.name}, {time.strftime('%Y-%m-%d %H:%M:%S %z')}", logfile)
        print("Start a Workout on the watch now, and sit in the recording position "
              "with the lamp on.", file=sys.stderr)
        if not record(args, base, logfile):
            log("No estimates recorded (an estimate needs 10 s); nothing to "
                "compare.", logfile)
            return
        t_end = time.time()
        report(check, logfile)

        export = args.watch
        if export is None:
            print(f"\nStop the Workout, then export the Health data to {args.downloads}"
                  " (Health > your picture > Export All Health Data). Waiting for it;"
                  " Ctrl+C to skip.", file=sys.stderr)
            try:
                export = wait_for_export(args.downloads, t_end)
            except KeyboardInterrupt:
                validate[3] = "<export.zip>"
                print("\nTo compare later, from tools/:\n  python -m "
                      + " ".join(validate), file=sys.stderr)
                return
            log(f"Health export: {export}", logfile)
        validate[3] = str(export.resolve())
        report(validate, logfile)


if __name__ == "__main__":
    main()
