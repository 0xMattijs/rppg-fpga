"""Read the board's eNVM back over the UART and save it.

The firmware's "dump" command (firmware/include/dump.h) sends the eNVM as
ENVM lines. This collects them, checks that every offset arrived and that the
CRC matches, and writes the bytes to a file:

    python -m rppg.envm_dump envm.bin
    python -m rppg.envm_dump envm.bin --compare ../firmware/build/rppg.hex
    python -m rppg.envm_dump head.bin --offset 0 --length 400

With --compare, it reports whether the eNVM holds the image in an Intel HEX
file, and what the bytes outside the image contain.
"""
import argparse
import base64
import sys
import time
import zlib

from .board import open_board

ENVM_SIZE = 256 * 1024
ENVM_BASE = 0x60000000
LINE_BYTES = 48


class DumpError(RuntimeError):
    pass


def read_dump(ser, offset, length, timeout_s):
    """Send "dump" and return the bytes, checked against the board's CRC."""
    ser.reset_input_buffer()
    ser.write(f"\ndump {offset:x} {length:x}\n".encode())
    ser.flush()

    data = bytearray()
    buf = b""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        buf += ser.read(4096)
        *lines, buf = buf.split(b"\n")
        for raw in lines:
            line = raw.decode("ascii", "replace").strip().lstrip("&")
            if line.startswith("# error"):
                raise DumpError(f"board: {line}")
            if not line.startswith("ENVM "):
                continue                    # frame CSV lines and comments
            fields = line.split()
            if fields[1] == "end":
                n, crc = int(fields[2]), int(fields[3], 16)
                if n != len(data):
                    raise DumpError(f"board sent {n} bytes, received {len(data)}")
                if zlib.crc32(data) != crc:
                    raise DumpError(f"CRC mismatch: board {crc:08x}, received {zlib.crc32(data):08x}")
                return bytes(data)
            off = int(fields[1], 16)
            if off != offset + len(data):
                raise DumpError(f"expected offset {offset + len(data):x}, got {off:x}; a line was lost")
            data += base64.b64decode(fields[2])
            if len(data) % (16 * 1024) < LINE_BYTES:
                print(f"\r{len(data) // 1024} / {length // 1024} KB", end="", file=sys.stderr, flush=True)
    raise DumpError(f"no end of dump after {timeout_s:.0f} s ({len(data)} bytes received)")


def read_hex(path):
    """Return {address: byte} from an Intel HEX file, with eNVM addresses
    (0x60000000 and up) moved to offsets from the start of the eNVM."""
    image, upper = {}, 0
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = bytes.fromhex(line[1:])
            if line[0] != ":" or sum(rec) & 0xFF:
                raise ValueError(f"{path}:{n}: bad record")
            count, addr, kind, payload = rec[0], int.from_bytes(rec[1:3], "big"), rec[3], rec[4:4 + rec[0]]
            if kind == 0:
                base = upper + addr
                if base >= ENVM_BASE:
                    base -= ENVM_BASE
                for i, b in enumerate(payload[:count]):
                    image[base + i] = b
            elif kind == 4:
                upper = int.from_bytes(payload, "big") << 16
            elif kind == 2:
                upper = int.from_bytes(payload, "big") << 4
            elif kind == 1:
                break
    return image


def compare(dump, offset, image):
    """Print how the dump matches the image and what lies outside it."""
    inside = [a for a in image if offset <= a < offset + len(dump)]
    diff = [a for a in inside if dump[a - offset] != image[a]]
    if not inside:
        print("the image has no bytes in the dumped range")
    elif diff:
        a = diff[0]
        print(f"MISMATCH: {len(diff)} of {len(inside)} image bytes differ; "
              f"first at {a:#x}: eNVM {dump[a - offset]:02x}, image {image[a]:02x}")
    else:
        print(f"match: all {len(inside)} image bytes ({min(inside):#x}..{max(inside):#x}) are in the eNVM")

    outside = [i for i in range(len(dump)) if offset + i not in image]
    if outside:
        values = {}
        for i in outside:
            values[dump[i]] = values.get(dump[i], 0) + 1
        common = ", ".join(f"{v:02x} x {c}" for v, c in sorted(values.items(), key=lambda kv: -kv[1])[:4])
        last = max((offset + i for i in outside if dump[i] not in (0x00, 0xFF)), default=None)
        print(f"outside the image: {len(outside)} bytes, most common {common}")
        if last is not None:
            print(f"  last byte that is neither 00 nor ff: {last:#x}")
    return not diff


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("out", help="file to write the eNVM bytes to")
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--offset", type=lambda s: int(s, 0), default=0)
    p.add_argument("--length", type=lambda s: int(s, 0), default=ENVM_SIZE)
    p.add_argument("--compare", metavar="HEX", help="Intel HEX image to check the eNVM against")
    p.add_argument("--timeout", type=float, default=60, help="seconds to wait for the whole dump")
    args = p.parse_args()
    if not (0 <= args.offset <= ENVM_SIZE and 0 < args.length <= ENVM_SIZE - args.offset):
        p.error("the range must lie inside the 256 KB eNVM")

    start = time.monotonic()
    with open_board(args.port) as ser:
        try:
            data = read_dump(ser, args.offset, args.length, args.timeout)
        except DumpError as e:
            sys.exit(f"\nerror: {e}")
    with open(args.out, "wb") as f:
        f.write(data)
    print(f"\r{len(data)} bytes from eNVM offset {args.offset:#x} in "
          f"{time.monotonic() - start:.0f} s, CRC ok, written to {args.out}", file=sys.stderr)

    if args.compare:
        return 0 if compare(data, args.offset, read_hex(args.compare)) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
