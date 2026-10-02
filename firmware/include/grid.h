#ifndef GRID_H
#define GRID_H

#include <stdint.h>

/* ROI grid and skin mask (Phase 6). The fabric splits the ROI into 4 x 4
 * cells and sums the skin pixels in each (hdl/src/grid_accumulator.v,
 * skin_mask.v). The DSP still uses the whole ROI's sums; for now the cells
 * go to the PC, while it's on, as one line per frame that capture.py
 * stores next to the CSV:
 *
 *   GRID <frame> <base64>   16 cells, row by row from the top left of the
 *                           camera image, 11 bytes each, big-endian: red,
 *                           green, and blue sums (3 bytes each) and the
 *                           pixel count (2 bytes)
 *
 * A calibration (SW3, console "calibrate") also fits the skin limits to
 * the person in the ROI: once the camera has locked, it measures the mean
 * color of the middle four cells with the mask off, centers the Cb and Cr
 * limits on it, and sets the Y floor to a fraction of its brightness. It
 * reports the result, or the old limits if the ROI was empty, as
 * "# skin <y_min> <y_max> <cb_min> <cb_max> <cr_min> <cr_max>". */

#define GRID_CELLS 16

/* Sets the limits from config.h. */
void grid_init(void);
/* GRID lines on or off. */
void grid_stream(int on);
int  grid_streaming(void);
/* Skin limits, inclusive, 0..255. They apply from the frame after next. */
void grid_set_skin(const uint8_t lim[6]);   /* y_min y_max cb_min cb_max cr_min cr_max */
/* 1: the cells sum skin pixels only; 0: every pixel. */
void grid_set_mask(int on);
/* Starts fitting the limits; call once the camera has locked. */
void grid_fit(void);
int  grid_fitting(void);

/* SysTick handler, after it has read a new frame's sums: grid_read() reads
 * the cells, if anything needs them, and grid_commit() keeps them once the
 * handler has checked that the frame didn't change during the read. */
void grid_read(void);
void grid_commit(uint32_t frame);

/* Main loop, once per frame from the queue, after its CSV line: sends the
 * frame's GRID line and feeds the fit. */
void grid_frame(uint32_t frame);

#endif
