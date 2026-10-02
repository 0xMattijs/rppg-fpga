"""Show the board's camera on the PC: an 80 x 60 thumbnail, about one a second.

    python -m rppg.preview                # mirrored, like the LCD
    python -m rppg.preview --save p.png   # also write each image to a file

The firmware sends the thumbnail as IMG lines while the preview is on
(firmware/include/preview.h). This script turns it on, draws the ROI with
its 4 x 4 grid and the latest estimate, and turns it off again when the
window closes or on Ctrl+C. The title shows how much of the ROI the skin
mask keeps; M dims the pixels it drops.
It needs the serial port to itself, so stop capture.py first; capture.py
--preview and session.py show the same window while they record.
"""
import argparse
import base64
import sys

import numpy as np

from .board import LineReader, open_board, send

W, H, SCALE = 80, 60, 8      # thumbnail size; one pixel per 8 x 8 block


def rgb565(raw):
    """(RGB image, skin mask) from a thumbnail row: RGB565 with the skin
    mask in bit 0."""
    p = np.frombuffer(raw, dtype=">u2").astype(np.uint32)
    r, g, b = p >> 11 & 31, p >> 5 & 63, p & 30
    rgb = np.stack([r * 255 // 31, g * 255 // 63, b * 255 // 31], -1).astype(np.uint8)
    return rgb, (p & 1).astype(bool)


class Preview:
    """The preview window. Pass it every line from the board with feed(),
    and call pump() often to keep the window responsive."""

    def __init__(self, mirror=True, save=None, title="rPPG camera preview"):
        import matplotlib
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        self.plt = plt
        # The keys are ours (session.py); drop matplotlib's shortcuts, such
        # as Q to close the window and S to save.
        for k in [k for k in matplotlib.rcParams if k.startswith("keymap.")]:
            matplotlib.rcParams[k] = []
        self.mirror = mirror
        self.save = save
        self.img = np.zeros((H, W, 3), np.uint8)
        self.skin = np.zeros((H, W), bool)
        self.show_mask = False
        self.rows_seen = set()
        self.roi = None
        self.est = ""
        self.status = ""
        self.frames = 0
        self.keys = []

        self.fig, ax = plt.subplots(figsize=(8, 6.4))
        self.fig.canvas.manager.set_window_title(title)
        self.shown = ax.imshow(self.img, extent=(0, W * SCALE, H * SCALE, 0),
                               interpolation="nearest")
        self.box = Rectangle((0, 0), 0, 0, fill=False, ec="lime", lw=2)
        ax.add_patch(self.box)
        self.grid_lines = [ax.plot([], [], color="lime", lw=0.6, alpha=0.7)[0]
                           for _ in range(6)]
        ax.set_axis_off()
        self.title = ax.set_title("waiting for the board...")
        self.footer = self.fig.text(0.5, 0.02, "", ha="center", fontsize=12)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.tight_layout(rect=(0, 0.05, 1, 1))
        plt.show(block=False)
        # Don't pull the window to the front on every redraw, so the
        # terminal keeps the keyboard if the user goes back to it.
        matplotlib.rcParams["figure.raise_window"] = False

    def on_key(self, e):
        if e.key == "m":
            self.show_mask = not self.show_mask
            if self.frames:
                self.draw()
        else:
            self.keys.append(e.key)

    def alive(self):
        return self.plt.fignum_exists(self.fig.number)

    def set_status(self, text):
        if text != self.status:
            self.status = text
            self.footer.set_text(text)

    def pop_keys(self):
        keys, self.keys = self.keys, []
        return keys

    def feed(self, line):
        f = line.split()
        if line.startswith("IMG roi") and len(f) == 6:
            self.roi = [int(v) for v in f[2:]]
        elif line.startswith("IMG ") and len(f) == 3 and f[1].isdigit():
            row = int(f[1])
            try:
                data = base64.b64decode(f[2], validate=True)
            except ValueError:
                return                # a byte lost on the way
            if row < H and len(data) == 2 * W:
                self.img[row], self.skin[row] = rgb565(data)
                self.rows_seen.add(row)
            if row == H - 1:
                self.show_image()
        elif line.startswith("EST ") and len(f) == 6:
            self.est = f"{float(f[3]):.0f} bpm, quality {float(f[4]):.2f}"

    def skin_share(self):
        """Fraction of the thumbnail's pixels inside the ROI that are skin."""
        if not self.roi:
            return None
        x0, y0, x1, y1 = (v // SCALE for v in self.roi)
        inside = self.skin[y0:y1, x0:x1]
        return inside.mean() if inside.size else None

    def draw(self):
        img = self.img
        if self.show_mask:
            img = np.where(self.skin[..., None], img, img // 4)
        self.shown.set_data(img[:, ::-1] if self.mirror else img)
        if self.roi:
            x0, y0, x1, y1 = self.roi
            # The fabric's cell edges (grid_accumulator.v)
            w, h = x1 - x0, y1 - y0
            xs = [x0 + w // 4, x0 + w // 2, x0 + w // 2 + w // 4]
            ys = [y0 + h // 4, y0 + h // 2, y0 + h // 2 + h // 4]
            if self.mirror:
                x0, x1 = W * SCALE - x1, W * SCALE - x0
                xs = [W * SCALE - x for x in xs]
            self.box.set_bounds(x0, y0, x1 - x0, y1 - y0)
            for line, x in zip(self.grid_lines[:3], xs):
                line.set_data([x, x], [y0, y1])
            for line, y in zip(self.grid_lines[3:], ys):
                line.set_data([x0, x1], [y, y])

    def show_image(self):
        self.frames += 1
        self.draw()
        missing = H - len(self.rows_seen)
        share = self.skin_share()
        self.title.set_text(f"image {self.frames}"
                            + (f", {missing} rows missing" if missing else "")
                            + (f", skin {share:.0%} of the box" if share is not None else "")
                            + (f"   {self.est}" if self.est else ""))
        self.rows_seen.clear()
        if self.save:
            self.fig.savefig(self.save)

    def pump(self):
        self.plt.pause(0.01)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=460800)
    p.add_argument("--no-mirror", action="store_true",
                   help="show the camera's own orientation, not the LCD's")
    p.add_argument("--save", help="write each complete image to this file")
    args = p.parse_args()

    win = Preview(mirror=not args.no_mirror, save=args.save)
    with open_board(args.port, args.baud) as ser:
        send(ser, "preview 1")
        reader = LineReader(ser)
        try:
            while win.alive():
                for line in reader.lines():
                    win.feed(line)
                    if line.startswith("# error"):
                        print(line, file=sys.stderr)
                win.pump()
        except KeyboardInterrupt:
            pass
        finally:
            send(ser, "preview 0")


if __name__ == "__main__":
    main()
