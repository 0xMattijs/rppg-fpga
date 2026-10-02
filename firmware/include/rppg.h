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
void rppg_push(const rppg_sample_t *s);
/* Returns 0 when the window is full. Each call advances the smoothing,
 * so call it once every ESTIMATE_EVERY frames, not every frame. */
int  rppg_estimate(rppg_result_t *out);

#ifdef RPPG_HOST
const float *rppg_debug_pulse(void);       /* band-passed pulse, WINDOW_SAMPLES long */
#endif

#endif
