"""The serial link to the board, shared by capture.py, preview.py, and session.py.

The FPGA's UART reaches the PC through the on-board PIC32, which relays it
over USB once it has seen '&'. Lines from the firmware end in CR LF; the
PIC32 echoes the '&' in front of the first one.
"""
import time

import serial


def open_board(port="/dev/ttyACM0", baud=460800):
    """Open the port, put the PIC32 in relay mode, and return the port."""
    ser = serial.Serial(port, baud, timeout=0.02)
    ser.write(b"&")               # ignored if already in relay mode
    time.sleep(0.1)
    return ser


def send(ser, *commands):
    """Send console commands (firmware/include/console.h) to the firmware."""
    ser.write(b"".join(b"\n" + c.encode() for c in commands) + b"\n")
    ser.flush()


class LineReader:
    """Splits what the port has received into lines without blocking for
    longer than the port's timeout, so a GUI can keep running."""

    def __init__(self, ser):
        self.ser = ser
        self.buf = b""

    def lines(self):
        self.buf += self.ser.read(4096)
        *done, self.buf = self.buf.split(b"\n")
        return [raw.decode("ascii", "replace").strip().lstrip("&") for raw in done]
