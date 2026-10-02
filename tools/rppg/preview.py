"""Show the board's camera on the PC: an 80 x 60 thumbnail, about one a second.

    python -m rppg.preview                # mirrored, like the LCD
    python -m rppg.preview --save p.png   # also write each image to a file

The firmware sends the thumbnail as IMG lines while the preview is on
(firmware/include/preview.h). This script turns it on, draws the ROI and the
latest estimate, and turns it off again when the window closes or on Ctrl+C.
It needs the serial port to itself, so stop capture.py first.
"""
import argparse
import base64
import sys
import time

import numpy as np
import serial

W, H, SCALE = 80, 60, 8      # thumbnail size; one pixel per 8 x 8 block


def rgb565(raw):
    p = np.frombuffer(raw, dtype=">u2").astype(np.uint32)
    r, g, b = p >> 11 & 31, p >> 5 & 63, p & 31
    return np.stack([r * 255 // 31, g * 255 // 63, b * 255 // 31], -1).astype(np.uint8)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    p.add_argument("--no-mirror", action="store_true",
                   help="show the camera's own orientation, not the LCD's")
    p.add_argument("--save", help="write each complete image to this file")
    args = p.parse_args()

    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    img = np.zeros((H, W, 3), np.uint8)
    rows_seen = set()
    roi = None
    est = ""

    fig, ax = plt.subplots(figsize=(8, 6.4))
    fig.canvas.manager.set_window_title("rPPG camera preview")
    shown = ax.imshow(img, extent=(0, W * SCALE, H * SCALE, 0), interpolation="nearest")
    box = Rectangle((0, 0), 0, 0, fill=False, ec="lime", lw=2)
    ax.add_patch(box)
    ax.set_axis_off()
    title = ax.set_title("waiting for the board...")
    fig.tight_layout()
    plt.show(block=False)

    with serial.Serial(args.port, args.baud, timeout=0.02) as ser:
        ser.write(b"&")           # PIC32: relay mode; ignored if already in it
        time.sleep(0.1)
        ser.write(b"\npreview 1\n")
        buf = b""
        frames = 0
        try:
            while plt.fignum_exists(fig.number):
                buf += ser.read(4096)
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    line = raw.decode("ascii", "replace").strip().lstrip("&")
                    f = line.split()
                    if line.startswith("IMG roi") and len(f) == 6:
                        roi = [int(v) for v in f[2:]]
                    elif line.startswith("IMG ") and len(f) == 3 and f[1].isdigit():
                        row = int(f[1])
                        try:
                            data = base64.b64decode(f[2], validate=True)
                        except ValueError:
                            continue      # a byte lost on the way
                        if row < H and len(data) == 2 * W:
                            img[row] = rgb565(data)
                            rows_seen.add(row)
                        if row == H - 1:
                            frames += 1
                            show = img if args.no_mirror else img[:, ::-1]
                            shown.set_data(show)
                            if roi:
                                x0, y0, x1, y1 = roi
                                if not args.no_mirror:
                                    x0, x1 = W * SCALE - x1, W * SCALE - x0
                                box.set_bounds(x0, y0, x1 - x0, y1 - y0)
                            missing = H - len(rows_seen)
                            title.set_text(f"image {frames}"
                                           + (f", {missing} rows missing" if missing else "")
                                           + (f"   {est}" if est else ""))
                            rows_seen.clear()
                            if args.save:
                                fig.savefig(args.save)
                    elif line.startswith("EST ") and len(f) == 6:
                        est = f"{float(f[3]):.0f} bpm, quality {float(f[4]):.2f}"
                    elif line.startswith("# error"):
                        print(line, file=sys.stderr)
                plt.pause(0.01)
        except KeyboardInterrupt:
            pass
        finally:
            ser.write(b"\npreview 0\n")
            time.sleep(0.1)


if __name__ == "__main__":
    main()
