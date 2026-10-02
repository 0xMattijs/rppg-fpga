#ifndef RPPG_H
#define RPPG_H

#include <stdint.h>

typedef struct {
    uint32_t frame;
    uint32_t timestamp_us;
    float r, g, b;          /* per-pixel means for this frame */
} rppg_sample_t;

typedef struct {
    float bpm;              /* smoothed across estimates; show this one */
    float bpm_raw;          /* this window only; log it for validation */
    float quality;          /* peak power / total in-band power, 0..1 */
} rppg_result_t;

void rppg_init(void);
/* Adds a frame. Uses s->frame to fill gaps of up to MAX_GAP_FILL frames by
 * interpolation, and restarts the window after a longer gap. Returns 1 when
 * an estimate is due: the window is full and ESTIMATE_EVERY samples have
 * arrived since the last one. */
int  rppg_push(const rppg_sample_t *s);
/* Returns 0 with a result, -1 if the window is not full. Each call advances
 * the smoothing, so call it only when rppg_push() returns 1. */
int  rppg_estimate(rppg_result_t *out);

#ifdef RPPG_HOST
const float *rppg_debug_pulse(void);       /* band-passed pulse, WINDOW_SAMPLES long */
#endif

#endif
