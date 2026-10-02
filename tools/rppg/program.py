"""Program the Hello FPGA through its on-board PIC32, without a FlashPro.

The kit's USB port is an MCP2221 serial bridge to a PIC32 that runs
Microchip's DirectC programmer. Microchip drives it from a Windows-only GUI;
this module speaks the same protocol, worked out from that GUI and the PIC
firmware:

    host '%Ex'          leave relay mode, if capture.py left the PIC in it
    host '#'            PIC '#'
    host 's' 'a' 'e'    PIC 'h' 'k' 'r'
                        PIC 'A'   asks for the action
    host action byte    '1' info, '3' erase, '4' program, '5' verify, '7' verify digest
                        PIC 'F'   asks for the device family
    host '5'            SmartFusion2 / IGLOO2

Then, until DirectC prints "End DirectC Demo", the PIC sends:

    'P' len:u32 text    log text
    'D' off:u32 len:u32 data request; reply len:u32 + dat[off:off+len]
    'T'                 phase marker, no payload
    'R' pct:u8          progress of the current component

All integers are little-endian. If a session stops mid-request, the PIC waits
forever; unplug and replug the board to reset it.

After programming, power-cycle the board. Until then the camera is not set up
and the LCD shows static.
"""
import argparse
import re
import sys
import time

import serial

ACTIONS = {"info": b"1", "erase": b"3", "program": b"4", "verify": b"5"}
FAMILY_SF2 = b"5"


class ProtocolError(RuntimeError):
    pass


def _read(ser, n):
    data = ser.read(n)
    if len(data) < n:
        raise ProtocolError(f"timed out: wanted {n} bytes, got {data!r}")
    return data


def _expect(ser, send, want):
    ser.write(send)
    got = _read(ser, len(want))
    if got != want:
        raise ProtocolError(f"sent {send!r}, expected {want!r}, got {got!r}")


def connect(ser, tries=8):
    """Wake the PIC with '#' until it echoes."""
    # In relay mode the PIC passes '#' on to the FPGA; '%Ex' leaves it. Out of
    # relay mode, the PIC ignores all three bytes.
    ser.write(b"%Ex")
    time.sleep(0.3)
    ser.reset_input_buffer()
    for _ in range(tries):
        ser.write(b"#")
        if ser.read(1) == b"#":
            return
        time.sleep(1.4)
    raise ProtocolError("no echo from the PIC; unplug and replug the board")


def run(ser, action, dat, out=sys.stdout, silence_s=60):
    """Run one DirectC action, serving data requests from `dat`.

    Returns DirectC's exit code (0 is success).
    """
    connect(ser)
    _expect(ser, b"s", b"h")
    _expect(ser, b"a", b"k")
    _expect(ser, b"e", b"rA")
    _expect(ser, ACTIONS[action], b"F")
    ser.write(FAMILY_SF2)

    text = bytearray()
    last = time.monotonic()
    while b"End DirectC Demo" not in text:
        tag = ser.read(1)
        if not tag:
            if time.monotonic() - last > silence_s:
                raise ProtocolError(f"PIC silent for {silence_s} s")
            continue
        last = time.monotonic()
        if tag == b"P":
            n = int.from_bytes(_read(ser, 4), "little")
            msg = _read(ser, n)
            text += msg
            out.write(msg.decode("ascii", "replace").replace("\x00", ""))
            out.flush()
        elif tag == b"D":
            off = int.from_bytes(_read(ser, 4), "little")
            n = int.from_bytes(_read(ser, 4), "little")
            if off + n > len(dat):
                raise ProtocolError(f"request past end of file: {off}+{n} > {len(dat)}")
            ser.write(n.to_bytes(4, "little") + dat[off:off + n])
        elif tag == b"R":
            pct = _read(ser, 1)[0]
            if pct % 25 == 0:
                out.write(f" {pct}%")
                out.flush()
        elif tag != b"T":
            raise ProtocolError(f"unknown message {tag!r}")

    m = re.search(rb"Exit code =\s*\x00?\s*(\d+)", bytes(text))
    if not m:
        raise ProtocolError("no exit code in DirectC output")
    return int(m.group(1))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("action", choices=ACTIONS)
    p.add_argument("dat", help="DirectC programming file (.dat) exported by Libero")
    p.add_argument("--port", default="/dev/ttyACM0")
    args = p.parse_args()

    with open(args.dat, "rb") as f:
        dat = f.read()
    with serial.Serial(args.port, 460800, timeout=2) as ser:
        start = time.monotonic()
        try:
            code = run(ser, args.action, dat)
        except ProtocolError as e:
            sys.exit(f"\nerror: {e}")
    print(f"\n{args.action}: exit code {code} after {time.monotonic() - start:.0f} s")
    if args.action == "program" and code == 0:
        print("Unplug and replug the board to start the new design.")
    sys.exit(0 if code == 0 else 1)


if __name__ == "__main__":
    main()
