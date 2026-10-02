#include <stdint.h>
#include "m2sxxx.h"
#include "system_m2sxxx.h"
#include "config.h"
#include "rppg.h"
#include "OV7725.h"
#include "ili9488.h"

/* rppg_top registers (word offsets); see hdl/src/rppg_top.v */
#define REG_SUM_R      0
#define REG_SUM_G      1
#define REG_SUM_B      2
#define REG_COUNT      3
#define REG_FRAME      4
#define REG_TIMESTAMP  5
#define REG_GEOMETRY   6
#define REG_UART       9
#define UART_BUSY      (1u << 0)
#define UART_HOST_SEEN (1u << 1)   /* the PC has put the PIC32 in relay mode */

/* Frames buffered between the SysTick handler and the main loop. An
 * estimate takes a large fraction of a second in soft float, so this must
 * hold more frames than arrive during one estimate. Power of two. */
#define FRAME_QUEUE 32

typedef struct {
    uint32_t sum_r, sum_g, sum_b, count, frame, timestamp_us;
} frame_sums_t;

static volatile uint32_t *const roi = (volatile uint32_t *)ROI_ACC_BASE;

/* Single producer (SysTick), single consumer (main loop): the handler
 * writes only q_head, the main loop writes only q_tail. */
static frame_sums_t queue[FRAME_QUEUE];
static volatile uint32_t q_head, q_tail;
static volatile uint32_t queue_overflows;
static uint32_t last_seen_frame;

/* The fabric latches each frame's sums at VSYNC and holds them for a whole
 * frame (33 ms), and there is no fabric interrupt line, so poll at 1 kHz. */
void SysTick_Handler(void)
{
    uint32_t frame = roi[REG_FRAME];
    if (frame == last_seen_frame)
        return;

    frame_sums_t f;
    f.sum_r = roi[REG_SUM_R];
    f.sum_g = roi[REG_SUM_G];
    f.sum_b = roi[REG_SUM_B];
    f.count = roi[REG_COUNT];
    f.timestamp_us = roi[REG_TIMESTAMP];
    /* A new frame landed mid-read: try again on the next tick. */
    if (roi[REG_FRAME] != frame)
        return;
    f.frame = frame;
    last_seen_frame = frame;

    uint32_t h = q_head;
    if (h - q_tail >= FRAME_QUEUE) {
        queue_overflows++;      /* shows up as a frame-counter gap */
        return;
    }
    queue[h % FRAME_QUEUE] = f;
    q_head = h + 1;
}

static void uart_putc(char c)
{
    while (roi[REG_UART] & UART_BUSY)
        ;
    roi[REG_UART] = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

static void uart_putu(uint32_t v)
{
    char buf[10];
    int n = 0;
    do {
        buf[n++] = '0' + v % 10;
        v /= 10;
    } while (v);
    while (n)
        uart_putc(buf[--n]);
}

int main(void)
{
    /* The camera first: OV7725_init() settles exposure for 2 s and then
     * locks it. The LCD then switches from its start-up screen to video. */
    OV7725_init();
    ILI9488_init();

    last_seen_frame = roi[REG_FRAME];
    SysTick_Config(SystemCoreClock / 1000);

#if ENABLE_DSP
    rppg_init();
#endif
    int geometry_sent = 0;

    for (;;) {
        if (q_tail == q_head)
            continue;
        frame_sums_t f = queue[q_tail % FRAME_QUEUE];
        q_tail++;

        /* Until the PIC32 relays, a byte sent to it overruns its UART, which
         * then stops receiving until the board is power-cycled. */
        if (!(roi[REG_UART] & UART_HOST_SEEN))
            continue;

        /* One comment line with the camera geometry, for checking the setup.
         * capture.py skips lines that don't have six fields. */
        if (!geometry_sent) {
            uint32_t g = roi[REG_GEOMETRY];
            uart_puts("# lines ");
            uart_putu(g & 0x3FF);
            uart_puts(", pixels per line ");
            uart_putu(g >> 16);
            uart_puts("\r\n");
            geometry_sent = 1;
        }

        /* frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count (docs/plan.md) */
        uart_putu(f.frame);         uart_putc(',');
        uart_putu(f.timestamp_us);  uart_putc(',');
        uart_putu(f.sum_r);         uart_putc(',');
        uart_putu(f.sum_g);         uart_putc(',');
        uart_putu(f.sum_b);         uart_putc(',');
        uart_putu(f.count);
        uart_puts("\r\n");

#if ENABLE_DSP
        if (f.count == 0)
            continue;
        rppg_sample_t s;
        rppg_result_t res;
        s.frame = f.frame;
        s.timestamp_us = f.timestamp_us;
        s.r = (float)f.sum_r / f.count;
        s.g = (float)f.sum_g / f.count;
        s.b = (float)f.sum_b / f.count;
        if (rppg_push(&s) && rppg_estimate(&res) == 0) {
            /* TODO(Phase 4): ui_show_bpm(res.bpm, res.quality); */
        }
#endif
    }
}
