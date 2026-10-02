"""Send console commands to the board and print its replies.

Each argument is one command line (see firmware/include/console.h):

    python -m rppg.send "test 1"
    python -m rppg.send "lcd 36 68" "roi 240 180 400 300"

Like capture.py, it puts the PIC32 in relay mode with '&'. The board then
streams frames too; only its comment lines ("# ...") are printed.
"""
import argparse
import sys
import time

import serial


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    p.add_argument("--wait", type=float, default=0.5,
                   help="seconds to wait for each reply")
    p.add_argument("commands", nargs="+")
    args = p.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.05) as ser:
        ser.write(b"&")           # PIC32: relay mode; ignored if already in it
        time.sleep(0.1)
        ser.write(b"\n")          # ends any partial line on the board
        failed = False
        for cmd in args.commands:
            ser.reset_input_buffer()
            ser.write(cmd.encode("ascii") + b"\n")
            deadline = time.time() + args.wait
            buf = b""
            while time.time() < deadline:
                buf += ser.read(4096)
                done = False
                for line in buf.decode("ascii", "replace").splitlines():
                    line = line.strip().lstrip("&")
                    if line.startswith("# ok") or line.startswith("# error"):
                        print(line)
                        failed |= line.startswith("# error")
                        done = True
                if done:
                    break
            else:
                print(f"no reply to {cmd!r}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
