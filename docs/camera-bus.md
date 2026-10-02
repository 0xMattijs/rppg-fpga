# Camera pixel bus

How the Hello FPGA reference design (`HF10_OV7725_LCD_FF`) receives video
from the OV7725, and how `hdl/src/cam_bus.v` adapts it for `roi_accumulator`.
Sources: `hdl/Write_LSRAM.vhd`, `hdl/double_flop.vhd`,
`component/work/TOP/TOP.v`, `component/work/line_write_read/line_write_read.v`,
`constraint/*.sdc`, and `SC/hellofpga_lcd_cam_ff/ov7725.c` in the reference
project.

## Clocks

| Clock | Source | Frequency | Use |
|-------|--------|-----------|-----|
| RC oscillator | On-chip `RCOSC_25_50MHZ` | 50 MHz | CCC reference |
| `GL0` | CCC, 50 × 24 / 12 | 100 MHz | All fabric logic, including capture |
| `GL1` → `XCLK` pin | CCC, 50 × 24 / 50 | 24 MHz | Camera master clock |

The camera's pixel clock (`PCLK_I`) is not used as a clock. The fabric samples
it on `GL0` and detects its rising edge, so all capture logic runs at 100 MHz.
Every clock comes from the on-chip RC oscillator, which is less accurate than
a crystal. Measure the real frame rate against the PC clock before trusting
`FRAME_RATE_HZ = 30` in `firmware/include/config.h`.

## Signals

| Pin | Width | Active | Synchronized? | Meaning |
|-----|-------|--------|---------------|---------|
| `PCLK_I` | 1 | Rising edge | Yes, 2 flops on `GL0` | Pixel byte clock |
| `H_REF_I` | 1 | High | Yes, 2 flops | Line data valid |
| `V_SYNC_I` | 1 | High | **No** | Frame start; resets all counters |
| `DATA_I` | 8 | n/a | Yes, 2 flops | One byte per `PCLK` rising edge |
| `XCLK` | 1 | n/a | Output | 24 MHz to the camera |
| `CAM_PWDN_O` | 1 | High | Output | Camera power-down, from `FF_GENERATOR` (Flash*Freeze) |

In the reference design, `V_SYNC_I` goes straight into `WRITE_LSRAM`
without a synchronizer. `cam_bus` now sits in front of `line_write_read` and
synchronizes it.

## Pixel format

The firmware sets `COM7 = 0x06`: VGA, RGB565. Each pixel is two bytes,
first byte first:

```
byte 0: R4 R3 R2 R1 R0 G5 G4 G3
byte 1: G2 G1 G0 B4 B3 B2 B1 B0
```

`WRITE_LSRAM` shifts each byte into the low half of a 16-bit register, so
after the second byte the word is `{byte0, byte1}`, and `[15:11]` is red,
`[10:5]` green, `[4:0]` blue. The byte pairing is counted from the rising
edge of `H_REF`, so a glitch on `PCLK` would swap bytes for the rest of the
line.

The reference design expands to 8 bits per channel by padding with zeros
(`{R, 3'b0}`, `{G, 2'b0}`, `{B, 3'b0}`). For summing, use the raw 5- and
6-bit values. Zero padding only scales them, and the per-channel sums fit
easily in 32 bits.

## What the LCD path changes

Leave these out of the ROI path:

- `WRITE_LSRAM` drops pixels to fit the 480 × 320 LCD. It writes only the
  bytes at counts 0, 2, and 4 of every 8 (3 of 4 pixels), and only lines at
  counts 0 and 1 of every 3 (2 of 3 lines).
- `Image_Enhancement` applies brightness and color constants from the GUI.

## The adapter: `cam_bus`

`cam_bus` takes the camera pins and does three things on `GL0`:

1. Passes all four signals on to `line_write_read`, three flops later. Each
   signal gets the same delay, so the LCD path samples at the same phase as
   before.
2. Samples each byte at `WRITE_LSRAM`'s phase, counts bytes from the `H_REF`
   rising edge and lines from `V_SYNC`, and emits one pixel per two bytes,
   with each channel padded to 8 bits.
3. Replaces the bytes in a 4-pixel border just outside the ROI with green,
   in the LCD copy only. The LCD drops 1 in 4 pixels and 1 in 3 lines, so a
   thinner border could vanish.

A `V_SYNC` rise ends one frame and starts the next: `roi_accumulator`
latches the sums and clears its accumulators in the same cycle.
`hdl/sim/tb_rppg_top.v` checks the sums and every byte the LCD path sees.

## Measured on the board

- 480 lines of 640 pixels, from the `GEOMETRY` register.
- 30.01 fps by the fabric's microsecond counter, with no dropped frames in
  65 s. The counter runs from the same RC oscillator as the camera clock, so
  check the rate against the PC clock before trusting it to better than a
  percent.
- Byte order: the LCD colors look right, and a skin-toned ROI averages
  R 109, G 97, B 90, so `{byte0, byte1}` is R5 G6 B5 as above.
  `COM3 = 0x90` flips the image vertically (bit 7).
