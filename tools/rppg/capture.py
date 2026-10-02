"""Record per-frame ROI sums from the board's UART to CSV."""
import argparse
import sys

import serial


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with serial.Serial(args.port, args.baud, timeout=1) as ser, open(args.out, "w") as f:
        f.write("frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count\n")
        print(f"Recording to {args.out}; press Ctrl+C to stop.", file=sys.stderr)
        try:
            while True:
                line = ser.readline().decode("ascii", "replace").strip()
                if line.count(",") == 5:
                    f.write(line + "\n")
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
