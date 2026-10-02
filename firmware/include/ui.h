#ifndef UI_H
#define UI_H

#include <stdint.h>

/* Display overlay (Phase 4). The fabric draws it into the camera image
 * (hdl/src/overlay.v); these functions only set its registers. */

/* Clears the waveform, shows "---", and turns the overlay on. */
void ui_init(void);
/* Adds one frame's mean green to the scrolling waveform. Called from the
 * SysTick handler for every frame, so the waveform keeps moving while an
 * estimate runs. */
void ui_frame(uint32_t sum_g, uint32_t count);
/* Shows a BPM estimate and its quality (rppg_result_t). */
void ui_show_bpm(float bpm, float quality);
/* Shows "---" and an empty quality bar: no estimate yet. */
void ui_show_none(void);
/* Replaces the whole image with color bars and one patch per RGB565 bit, for
 * checking the LCD's colors and data lines (hdl/src/overlay.v). */
void ui_set_test(int on);
/* Color gains of the LCD path, 0x80 = 1.0 (rppg_top COLOR_GAIN). */
void ui_set_gain(uint32_t r, uint32_t g, uint32_t b);
int  ui_test(void);
/* Digit and waveform colors, RGB565 (rppg_top OVL_COLOR). */
void ui_set_colors(uint32_t digit, uint32_t wave);

#endif
