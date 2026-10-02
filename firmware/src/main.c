#include <stdint.h>
#include "config.h"
#include "rppg.h"

/* roi_accumulator register map (word offsets) */
#define REG_SUM_R   0
#define REG_SUM_G   1
#define REG_SUM_B   2
#define REG_COUNT   3
#define REG_FRAME   4

static volatile uint32_t *const roi = (volatile uint32_t *)ROI_ACC_BASE;
static volatile int frame_ready;

/* TODO(Phase 2): attach to the fabric interrupt line Libero assigns. */
void FabricIrq0_IRQHandler(void)
{
    frame_ready = 1;
}

int main(void)
{
    rppg_sample_t s;
    rppg_result_t res;

    /* TODO(Phase 1): clock, UART and display init from the reference design. */
    rppg_init();

    for (;;) {
        if (!frame_ready)
            continue;
        frame_ready = 0;

        uint32_t n = roi[REG_COUNT];
        if (n == 0)
            continue;
        s.frame = roi[REG_FRAME];
        s.timestamp_us = 0;   /* TODO: timestamp in fabric (see risks) */
        s.r = (float)roi[REG_SUM_R] / n;
        s.g = (float)roi[REG_SUM_G] / n;
        s.b = (float)roi[REG_SUM_B] / n;

        /* TODO(Phase 2): print "frame,ts,r,g,b,n" over UART. */
        rppg_push(&s);

        if (rppg_estimate(&res) == 0) {
            /* TODO(Phase 4): ui_show_bpm(res.bpm, res.quality); */
        }
    }
}
