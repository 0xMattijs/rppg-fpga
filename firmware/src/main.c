#include <stdint.h>
#include "config.h"
#include "rppg.h"

/* roi_accumulator register map (word offsets) */
#define REG_SUM_R   0
#define REG_SUM_G   1
#define REG_SUM_B   2
#define REG_COUNT   3
#define REG_FRAME   4

/* Frames buffered between the IRQ and the main loop. An estimate takes a
 * large fraction of a second in soft float, so this must hold more frames
 * than arrive during one estimate. Power of two. */
#define FRAME_QUEUE 32

typedef struct {
    uint32_t sum_r, sum_g, sum_b, count, frame;
} frame_sums_t;

static volatile uint32_t *const roi = (volatile uint32_t *)ROI_ACC_BASE;

/* Single producer (IRQ), single consumer (main loop): the IRQ writes only
 * q_head, the main loop writes only q_tail. */
static frame_sums_t queue[FRAME_QUEUE];
static volatile uint32_t q_head, q_tail;
static volatile uint32_t queue_overflows;

/* Frames lost before they reached rppg_push(), from gaps in the fabric
 * frame counter. rppg_push() fills short gaps; this counts them for the log. */
static uint32_t frames_dropped;

/* TODO(Phase 2): attach to the fabric interrupt line Libero assigns.
 * Read the latched sums here, before the next frame end overwrites them. */
void FabricIrq0_IRQHandler(void)
{
    uint32_t h = q_head;
    if (h - q_tail >= FRAME_QUEUE) {
        queue_overflows++;      /* shows up as a frame-counter gap */
        return;
    }
    frame_sums_t *f = &queue[h % FRAME_QUEUE];
    f->sum_r = roi[REG_SUM_R];
    f->sum_g = roi[REG_SUM_G];
    f->sum_b = roi[REG_SUM_B];
    f->count = roi[REG_COUNT];
    f->frame = roi[REG_FRAME];
    q_head = h + 1;
}

int main(void)
{
    rppg_sample_t s;
    rppg_result_t res;
    int have_frame = 0;
    uint32_t last_frame = 0;

    /* TODO(Phase 1): clock, UART and display init from the reference design. */
    rppg_init();

    for (;;) {
        if (q_tail == q_head)
            continue;
        frame_sums_t f = queue[q_tail % FRAME_QUEUE];
        q_tail++;

        if (have_frame && f.frame - last_frame > 1)
            frames_dropped += f.frame - last_frame - 1;
        have_frame = 1;
        last_frame = f.frame;

        /* TODO(Phase 2): print "frame,ts,sum_r,sum_g,sum_b,count" over UART. */
        if (f.count == 0)
            continue;
        s.frame = f.frame;
        s.timestamp_us = 0;   /* TODO: timestamp in fabric (see risks) */
        s.r = (float)f.sum_r / f.count;
        s.g = (float)f.sum_g / f.count;
        s.b = (float)f.sum_b / f.count;
        if (rppg_push(&s) && rppg_estimate(&res) == 0) {
            /* TODO(Phase 4): ui_show_bpm(res.bpm, res.quality); */
        }
    }
}
