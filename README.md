# rppg-fpga

A contactless heart-rate monitor on the Hello FPGA board (Microchip SmartFusion2).
It reads your pulse from a live camera image of your face by using remote
photoplethysmography (rPPG), and it shows BPM on the kit's touch display.

The design rule: per-pixel work runs in FPGA fabric, and per-frame work runs on
the Cortex-M3.

```
camera ──► fabric: ROI / skin mask / RGB accumulators ──► per-frame sums
                                                              │ (APB, polled)
                                                              ▼
            display ◄── Cortex-M3: normalize ─ POS ─ band-pass ─ FFT ─ BPM
                                                              │
            PC: capture.py ◄── UART ──────────────────────────┘
                 validate.py ◄── Apple Watch heart rate (Health export, ground truth)
```

## Repository layout

| Path | Contents |
|------|----------|
| `hdl/src/` | Fabric modules (Verilog): ROI accumulator, later skin mask and ROI grid |
| `hdl/sim/` | Testbenches |
| `libero/` | Libero SoC project notes; generated project files stay out of Git |
| `firmware/` | Cortex-M3 C code (SoftConsole): frame IRQ, DSP, UI, drivers |
| `tools/` | Python: UART capture, POS prototype, validation analysis |
| `data/` | Recorded sessions (ignored by Git) |
| `docs/` | Project plan and notes |

## Status

See [docs/plan.md](docs/plan.md) for the seven-phase build plan.

- [x] Phase 1: Reference design
- [x] Phase 2: ROI accumulator in fabric
- [x] Phase 3: Signal processing on the Cortex-M3
- [x] Phase 4: Display UI (buttons; the touch panel is not wired)
- [ ] Phase 5: Validation against an Apple Watch
- [ ] Phase 6: Multi-ROI grid and skin detection
- [ ] Phase 7: Pulse visualization (stretch)

## PC tools

On Linux, stop ModemManager from probing the board's USB serial port
(Microchip MCP2221). Its AT commands reach the FPGA through the PIC32, which
can stall the serial link and used to change the LCD colors:

```bash
echo 'ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="00dd", ENV{ID_MM_DEVICE_IGNORE}="1"' \
  | sudo tee /etc/udev/rules.d/99-hello-fpga.rules
sudo udevadm control --reload-rules
```

```bash
cd tools
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Program the board through its on-board PIC (no FlashPro needed)
python -m rppg.program program ../libero/build/export/rppg.dat

# Record per-frame sums and the board's BPM estimates (through the same PIC,
# /dev/ttyACM0); the estimates go to ../data/session.est
python -m rppg.capture --out ../data/session.csv

# Check the board's estimates against the host build of the same C code
python -m rppg.check_board ../data/session.csv

# See the camera on the PC (80 x 60, about once a second) to place your face
# in the ROI; close the window before capturing
python -m rppg.preview

# Send console commands: color test pattern, ROI, raw LCD commands
python -m rppg.send "test 1" "roi 240 180 400 300"

# Check a recording: frame rate, dropped frames, band-passed green channel
python -m rppg.raw ../data/session.csv --plot

# Estimate BPM offline with POS
python -m rppg.pos ../data/session.csv --plot

# Make a synthetic session, with drift, flicker, motion, and dropped frames
python -m rppg.synth ../data/synth.csv --bpm 72 --realistic

# Score POS against the true BPM as each effect grows (about 1 minute)
python -m rppg.stress

# Compare with an Apple Watch: start a Workout on the watch, record with
# capture.py, then export from the Health app (Phase 5)
python -m rppg.validate ../data/session.est --watch export.zip --plot session.png
```
