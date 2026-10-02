"""Record per-frame ROI sums from the board's UART to CSV.

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
"""
import argparse
import sys
import time
from pathlib import Path

import serial


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    est_path = Path(args.out).with_suffix(".est")
    with serial.Serial(args.port, args.baud, timeout=1) as ser, \
            open(args.out, "w") as f, open(est_path, "w") as est:
        f.write("frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count\n")
        ser.write(b"&")           # PIC32: relay mode; ignored if already in it
        time.sleep(0.1)
        ser.write(b"\nrestart\n")  # relayed to the FPGA (firmware/include/console.h)
        print(f"Recording to {args.out}; press Ctrl+C to stop.", file=sys.stderr)
        rows = 0
        start = None              # frame of "# restart"; nothing is kept before it
        try:
            while True:
                # The PIC32 echoes the "&" in front of the first line.
                line = ser.readline().decode("ascii", "replace").strip().lstrip("&")
                if line.startswith("#"):
                    print(line, file=sys.stderr)
                    if line.startswith("# restart ") and start is None:
                        start = int(line.split()[2])
                elif start is None:
                    continue
                elif line.startswith("EST ") and len(line.split()) == 6:
                    est.write(line + "\n")
                    _, frame, bpm_raw, bpm, quality, us = line.split()
                    print(f"frame {frame}: {bpm} bpm (this window {bpm_raw}, "
                          f"quality {quality}, {int(us) / 1000:.0f} ms)", file=sys.stderr)
                elif (line.count(",") == 5 and line.split(",")[0].isdigit()
                      and int(line.split(",")[0]) >= start):
                    f.write(line + "\n")
                    rows += 1
                    if rows % 300 == 0:
                        print(f"{rows} frames", file=sys.stderr)
        except KeyboardInterrupt:
            pass
        print(f"{rows} frames recorded; estimates in {est_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
