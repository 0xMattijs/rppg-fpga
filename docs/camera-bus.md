# Camera pixel bus

How the Hello FPGA reference design (`HF10_OV7725_LCD_FF`) receives video
from the OV7725, and what the Phase 2 adapter for `roi_accumulator` must do.
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

`V_SYNC_I` goes straight into `WRITE_LSRAM` without a synchronizer. The
adapter must add two flops for it.

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

Tap the bus after `double_flop` and before `WRITE_LSRAM` to get every pixel
of the 640 × 480 frame, unchanged.

## Adapter for `roi_accumulator`

`roi_accumulator` expects `frame_start`, `frame_end`, `pix_valid`, `pix_x`,
`pix_y`, and 8-bit `pix_r/g/b`. Build them on `GL0`:

1. Synchronize `V_SYNC_I` with two flops.
2. `frame_start`: rising edge of synchronized `V_SYNC`.
   `frame_end`: falling edge of `H_REF` on line 479, or the next
   `V_SYNC` rise.
3. Count bytes from each `H_REF` rising edge. Every second byte completes a
   pixel: assert `pix_valid` for one cycle, and increment `pix_x`.
4. Reset `pix_x` at each `H_REF` rising edge. Increment `pix_y` at each
   `H_REF` falling edge, and reset it at `frame_start`.
5. Expand channels with `CW = 8` by zero padding, as above, or set `CW` to
   6 and pass the raw values. Either works for POS, which normalizes each
   channel.

## Open checks on hardware

- Measure the frame rate and line count. Expect 30 fps and 480 lines, but
  `CLKRC`, `COM4`, and the RC oscillator all affect the frame rate.
- `COM3 = 0x90` flips the image vertically (bit 7). Bit 4's effect on byte
  order is unconfirmed. The LCD colors look right, which suggests the order
  above is correct.
