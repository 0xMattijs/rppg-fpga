#ifndef CONFIG_H
#define CONFIG_H

#define FRAME_RATE_HZ      30
#define WINDOW_SAMPLES     300   /* 10 s at 30 fps */
#define FFT_SIZE           512
#define HR_MIN_MHZ         700   /* 42 bpm; whole mHz so #if can compare it */
#define HR_MAX_MHZ         4000  /* 240 bpm */
#define HR_MIN_HZ          (HR_MIN_MHZ / 1000.0f)
#define HR_MAX_HZ          (HR_MAX_MHZ / 1000.0f)
#define POS_WINDOW         48    /* ~1.6 s, per Wang et al. 2017 */
#define ESTIMATE_EVERY     30    /* frames between estimates: 1 s at 30 fps */
#define BPM_SMOOTH_ALPHA   0.3f  /* EMA weight of each new estimate; tied to ESTIMATE_EVERY */
#define MAX_GAP_FILL       5     /* longest frame-counter gap filled by interpolation;
                                    a longer gap restarts the window */
#define HARMONIC_RATIO     0.25f /* report half the peak frequency when its power is at
                                    least this fraction of the peak's */

/* Display overlay (Phase 4, firmware/src/ui/ui.c) */
#define UI_MIRROR          1     /* 1 if the LCD shows the camera image mirrored;
                                    flips the overlay so the digits read right */
/* LCD color gains (rppg_top COLOR_GAIN), 0x80 = 1.0, up to 0x3FF. Try others
 * live with "gain <r> <g> <b>" (rppg.send). */
#define LCD_GAIN_R         0x80
#define LCD_GAIN_G         0x80
#define LCD_GAIN_B         0x80
/* Digit and waveform colors, RGB565. The panel's green is strong: full white
 * looks mint, and red with even half green looks green. Hence less green in
 * the white, and yellow at 24 of 63 green. Try others live with
 * "color <digit> <wave>" (rppg.send). */
#define UI_DIGIT_COLOR     0xFE5A
#define UI_WAVE_COLOR      0xFB00
#define UI_YELLOW          0xFB00   /* quality bar, middle range */

/* Quality bar. First guesses: Phase 3 saw 0.03-0.18 on a face; tune them
 * against the M5 sensor in Phase 5. */
#define QUALITY_FULL       0.4f  /* quality that fills the bar */
#define QUALITY_LOW        0.08f /* below: red bar */
#define QUALITY_GOOD       0.15f /* at or above: green bar; between: yellow */
#define WAVE_HP_ALPHA      0.0625f /* waveform high-pass: EMA weight per frame (~0.3 Hz) */
#define WAVE_MIN_AMP       0.0005f /* smallest waveform full scale, as a fraction of the
                                      mean green, so a still image draws a flat line */

/* Fabric APB base of rppg_top (hdl/src/rppg_top.v) on the FIC_0 bus. */
#define ROI_ACC_BASE       0x30001000u

/* Run POS and the FFT on the board (Phase 3) and send an EST line per
 * estimate. Off, the firmware only streams per-frame sums over UART. */
#define ENABLE_DSP         1

#endif
