"""Record per-frame ROI sums from the board's UART to CSV.

The FPGA sends at 230400 baud to the on-board PIC32, which passes the bytes
on over USB (/dev/ttyACM0, 460800 baud) once it is in relay mode. This
script sends '&' to enter relay mode, then one byte that the PIC32 relays to
the FPGA: the firmware stays quiet until it sees it. Leave relay mode with
'%Ex'; program.py does that itself.
"""
import argparse
import sys
import time

import serial


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with serial.Serial(args.port, args.baud, timeout=1) as ser, open(args.out, "w") as f:
        f.write("frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count\n")
        ser.write(b"&")           # PIC32: relay mode; ignored if already in it
        time.sleep(0.1)
        ser.write(b"s")           # relayed to the FPGA: start streaming
        print(f"Recording to {args.out}; press Ctrl+C to stop.", file=sys.stderr)
        rows = 0
        try:
            while True:
                # The PIC32 echoes the "&" in front of the first line.
                line = ser.readline().decode("ascii", "replace").strip().lstrip("&")
                if line.startswith("#"):
                    print(line, file=sys.stderr)
                elif line.count(",") == 5:
                    f.write(line + "\n")
                    rows += 1
                    if rows % 300 == 0:
                        print(f"{rows} frames", file=sys.stderr)
        except KeyboardInterrupt:
            pass
        print(f"{rows} frames recorded", file=sys.stderr)


if __name__ == "__main__":
    main()
