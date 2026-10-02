"""Record per-frame ROI sums from the board's UART to CSV.

    python -m rppg.capture --out ../data/session.csv
    python -m rppg.capture --out ../data/session.csv --preview   # show the camera too

The FPGA sends at 230400 baud to the on-board PIC32, which passes the bytes
on over USB (/dev/ttyACM0, 460800 baud) once it is in relay mode. This
script sends '&' to enter relay mode, then a "restart" command that the
PIC32 relays to the FPGA: the firmware stays quiet until it sees a byte from
the PC. The board restarts its estimates at the next frame and reports that
frame ("# restart <frame>"); the recording starts there, so rppg.check_board
can repeat the estimates from it. Leave relay mode with
'%Ex'; program.py does that itself.

The board's own BPM estimates (EST lines) go to a second file next to the
CSV, with the extension .est; rppg.check_board compares them with the PC.
Each line gets one more field: the PC's clock (Unix seconds) at the end of
the estimate's window, the time the line arrived less the time the estimate
took. rppg.validate matches it against a watch's heart rate.

With --preview, the camera preview (rppg.preview) stays on during the
recording, and the first whole image is saved next to the CSV as
<name>_frame.png, a record of the framing. Closing the window stops the
recording.
"""
import argparse
import sys
import time
from pathlib import Path

from .board import LineReader, open_board, send


def log(msg, file=None):
    print(msg, file=sys.stderr)
    if file:
        file.write(msg + "\n")
        file.flush()


class Recorder:
    """Writes the frames and estimates that follow the board's
    "# restart <frame>" to <out> and <out>.est. Pass it every line from the
    board with feed(); board messages go to stderr and to logfile."""

    def __init__(self, out, logfile=None):
        self.out = Path(out)
        self.est_path = self.out.with_suffix(".est")
        self.f = open(self.out, "w")
        self.est = open(self.est_path, "w")
        self.logfile = logfile
        self.f.write("frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count\n")
        self.rows = 0
        self.start = None         # frame of "# restart"; nothing is kept before it

    def feed(self, line):
        if line.startswith("#"):
            log(line, self.logfile)
            if line.startswith("# restart ") and self.start is None:
                self.start = int(line.split()[2])
        elif self.start is None:
            return
        elif line.startswith("EST ") and len(line.split()) == 6:
            _, frame, bpm_raw, bpm, quality, us = line.split()
            self.est.write(f"{line} {time.time() - int(us) / 1e6:.3f}\n")
            self.est.flush()
            log(f"frame {frame}: {bpm} bpm (this window {bpm_raw}, "
                f"quality {quality}, {int(us) / 1000:.0f} ms)", self.logfile)
        elif (line.count(",") == 5 and line.split(",")[0].isdigit()
              and int(line.split(",")[0]) >= self.start):
            self.f.write(line + "\n")
            self.rows += 1
            if self.rows % 300 == 0:
                log(f"{self.rows} frames", self.logfile)

    def close(self):
        self.f.close()
        self.est.close()
        log(f"{self.rows} frames recorded; estimates in {self.est_path}", self.logfile)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    p.add_argument("--out", required=True)
    p.add_argument("--preview", action="store_true",
                   help="show the camera while recording (mirrored, like the LCD)")
    args = p.parse_args()

    win = None
    if args.preview:
        from .preview import Preview
        win = Preview(title=f"rPPG recording: {Path(args.out).name}")
        win.set_status("recording; close this window or press Ctrl+C to stop")
    rec = Recorder(args.out)
    out = Path(args.out)
    snapshot = out.with_name(out.stem + "_frame.png")
    saved = False
    with open_board(args.port, args.baud) as ser:
        # Relayed to the FPGA (firmware/include/console.h).
        send(ser, f"preview {int(args.preview)}", "restart")
        print(f"Recording to {args.out}; press Ctrl+C to stop.", file=sys.stderr)
        reader = LineReader(ser)
        try:
            while win is None or win.alive():
                for line in reader.lines():
                    rec.feed(line)
                    if win:
                        win.feed(line)
                        if win.frames and not saved:
                            win.fig.savefig(snapshot)
                            saved = True
                if win:
                    win.pump()
        except KeyboardInterrupt:
            pass
        finally:
            if args.preview:
                send(ser, "preview 0")
            rec.close()


if __name__ == "__main__":
    main()
