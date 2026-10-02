# rppg-fpga

A contactless heart-rate monitor on the Hello FPGA board (Microchip SmartFusion2).
It reads your pulse from a live camera image of your face by using remote
photoplethysmography (rPPG), and it shows BPM on the kit's touch display.

The design rule: per-pixel work runs in FPGA fabric, and per-frame work runs on
the Cortex-M3.

```
camera ──► fabric: ROI / skin mask / RGB accumulators ──► per-frame sums
                                                              │ (APB + IRQ)
                                                              ▼
            display ◄── Cortex-M3: normalize ─ POS ─ band-pass ─ FFT ─ BPM
                                                              ▲
                                       M5 heart-rate unit ────┘ (I2C, ground truth)
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
- [ ] Phase 2: ROI accumulator in fabric
- [ ] Phase 3: Signal processing on the Cortex-M3
- [ ] Phase 4: Touch UI
- [ ] Phase 5: Validation with the M5 sensor
- [ ] Phase 6: Multi-ROI grid and skin detection
- [ ] Phase 7: Pulse visualization (stretch)

## PC tools

```bash
cd tools
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Program the board through its on-board PIC (no FlashPro needed)
python -m rppg.program program ../libero/build/export/rppg_ref.dat

# Record per-frame sums from the board
python -m rppg.capture --port /dev/ttyUSB0 --out ../data/session.csv

# Estimate BPM offline with POS
python -m rppg.pos ../data/session.csv --plot

# Make a synthetic session, with drift, flicker, motion, and dropped frames
python -m rppg.synth ../data/synth.csv --bpm 72 --realistic

# Score POS against the true BPM as each effect grows (about 1 minute)
python -m rppg.stress

# Compare against the M5 reference (Phase 5)
python -m rppg.validate ../data/log.csv
```
