/* rPPG pipeline (Phase 3). Port of tools/rppg/pos.py; keep the two in step. */
#include "rppg.h"
#include "config.h"

static rppg_sample_t window[WINDOW_SAMPLES];
static int head, filled;

void rppg_init(void)
{
    head = 0;
    filled = 0;
}

void rppg_push(const rppg_sample_t *s)
{
    window[head] = *s;
    head = (head + 1) % WINDOW_SAMPLES;
    if (filled < WINDOW_SAMPLES)
        filled++;
}

int rppg_estimate(rppg_result_t *out)
{
    if (filled < WINDOW_SAMPLES)
        return -1;

    /* TODO(Phase 3):
     * 1. POS projection with overlap-add over POS_WINDOW samples
     * 2. Band-pass HR_MIN_HZ..HR_MAX_HZ
     * 3. Zero-pad to FFT_SIZE, CMSIS-DSP arm_rfft_fast_f32
     * 4. Strongest in-band peak -> BPM, smoothed across updates
     */
    out->bpm = 0.0f;
    out->quality = 0.0f;
    return -1;
}
