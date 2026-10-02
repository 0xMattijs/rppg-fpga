/* ROI grid and skin mask (Phase 6); see include/grid.h. */
#include <stdint.h>
#include "config.h"
#include "grid.h"
#include "uart.h"

/* rppg_top registers (word offsets); see hdl/src/rppg_top.v */
#define REG_FRAME    4
#define REG_SKIN_C   19
#define REG_SKIN_Y   20
#define REG_CELLS    (0x200 / 4)    /* 4 words per cell: red, green, blue, count */

/* Frames of cells between the SysTick handler and the main loop. The frame
 * queue in main.c is longer; a frame whose cells were overwritten goes
 * without its GRID line. Power of two. */
#define GRID_QUEUE   16

/* The middle four cells: what a calibration fits the skin limits to. */
static const uint8_t middle[4] = {5, 6, 9, 10};

typedef struct {
    volatile uint32_t frame;        /* NO_FRAME while being written */
    uint32_t v[GRID_CELLS][4];
} grid_slot_t;
#define NO_FRAME 0xFFFFFFFFu

static volatile uint32_t *const regs = (volatile uint32_t *)ROI_ACC_BASE;
static grid_slot_t ring[GRID_QUEUE];
static volatile uint32_t ring_head;     /* written by the SysTick handler only */
static uint32_t cells[GRID_CELLS][4];   /* the main loop's copy */

static int streaming, mask_on;
static uint8_t limits[6];

/* Fit: frames still to sum (0: not fitting), and the first one to use. */
static volatile int fit_left;
static uint32_t fit_from;
static float fit_r, fit_g, fit_b;
static int fit_frames;

static void write_limits(int mask)
{
    regs[REG_SKIN_C] = limits[2] | limits[3] << 8 | limits[4] << 16 |
                       (uint32_t)limits[5] << 24;
    regs[REG_SKIN_Y] = limits[0] | limits[1] << 8 | (uint32_t)(mask != 0) << 16;
}

static void report_limits(void)
{
    if (!uart_host_seen())
        return;
    uart_puts("# skin");
    for (int i = 0; i < 6; i++) {
        uart_putc(' ');
        uart_putu(limits[i]);
    }
    uart_puts("\r\n");
}

void grid_init(void)
{
    static const uint8_t lim[6] = {
        SKIN_Y_MIN, SKIN_Y_MAX, SKIN_CB_MIN, SKIN_CB_MAX, SKIN_CR_MIN, SKIN_CR_MAX,
    };
    mask_on = SKIN_MASK;
    grid_set_skin(lim);
    for (int i = 0; i < GRID_QUEUE; i++)
        ring[i].frame = NO_FRAME;
}

void grid_stream(int on)
{
    streaming = on;
}

int grid_streaming(void)
{
    return streaming;
}

void grid_set_skin(const uint8_t lim[6])
{
    for (int i = 0; i < 6; i++)
        limits[i] = lim[i];
    write_limits(mask_on && !fit_left);
}

void grid_set_mask(int on)
{
    mask_on = on;
    write_limits(mask_on && !fit_left);
}

void grid_fit(void)
{
    write_limits(0);
    /* The mask switches off at the next VSYNC, so the frame after the one
     * in progress is the first without it. */
    fit_from = regs[REG_FRAME] + 2;
    fit_r = fit_g = fit_b = 0.0f;
    fit_frames = 0;
    fit_left = SKIN_FIT_FRAMES;
}

int grid_fitting(void)
{
    return fit_left != 0;
}

void grid_read(void)
{
    if (!streaming && !fit_left)
        return;
    grid_slot_t *s = &ring[ring_head % GRID_QUEUE];
    s->frame = NO_FRAME;
    for (int c = 0; c < GRID_CELLS; c++)
        for (int k = 0; k < 4; k++)
            s->v[c][k] = regs[REG_CELLS + 4 * c + k];
}

void grid_commit(uint32_t frame)
{
    if (!streaming && !fit_left)
        return;
    ring[ring_head % GRID_QUEUE].frame = frame;
    ring_head++;
}

/* Copies the frame's cells to cells[]. Returns 0 if they are gone. */
static int find(uint32_t frame)
{
    for (int i = 0; i < GRID_QUEUE; i++) {
        grid_slot_t *s = &ring[i];
        if (s->frame != frame)
            continue;
        for (int c = 0; c < GRID_CELLS; c++)
            for (int k = 0; k < 4; k++)
                cells[c][k] = s->v[c][k];
        /* Overwritten while copying? */
        return s->frame == frame;
    }
    return 0;
}

static void send_line(uint32_t frame)
{
    uint8_t buf[GRID_CELLS * 11], *p = buf;
    for (int c = 0; c < GRID_CELLS; c++) {
        for (int k = 0; k < 3; k++) {
            *p++ = (uint8_t)(cells[c][k] >> 16);
            *p++ = (uint8_t)(cells[c][k] >> 8);
            *p++ = (uint8_t)cells[c][k];
        }
        *p++ = (uint8_t)(cells[c][3] >> 8);
        *p++ = (uint8_t)cells[c][3];
    }
    uart_puts("GRID ");
    uart_putu(frame);
    uart_putc(' ');
    uart_putbase64(buf, sizeof buf);
    uart_puts("\r\n");
}

static uint8_t clamp(float v)
{
    return v < 0.0f ? 0 : v > 255.0f ? 255 : (uint8_t)(v + 0.5f);
}

/* Adds the middle cells' mean color; sets the limits after the last frame. */
static void fit_frame(uint32_t frame)
{
    if ((int32_t)(frame - fit_from) < 0)
        return;
    uint32_t r = 0, g = 0, b = 0, n = 0;
    for (int i = 0; i < 4; i++) {
        r += cells[middle[i]][0];
        g += cells[middle[i]][1];
        b += cells[middle[i]][2];
        n += cells[middle[i]][3];
    }
    if (n) {
        fit_r += (float)r / n;
        fit_g += (float)g / n;
        fit_b += (float)b / n;
        fit_frames++;
    }
    if (--fit_left > 0)
        return;
    if (fit_frames == 0) {          /* empty ROI: keep the limits */
        write_limits(mask_on);
        report_limits();
        return;
    }
    float mr = fit_r / fit_frames, mg = fit_g / fit_frames, mb = fit_b / fit_frames;
    /* skin_mask.v's YCbCr */
    float y  = (77.0f * mr + 150.0f * mg + 29.0f * mb) / 256.0f;
    float cb = 128.0f + (-43.0f * mr - 85.0f * mg + 128.0f * mb) / 256.0f;
    float cr = 128.0f + (128.0f * mr - 107.0f * mg - 21.0f * mb) / 256.0f;
    uint8_t lim[6] = {
        clamp(y * SKIN_FIT_Y_FLOOR), SKIN_Y_MAX,
        clamp(cb - SKIN_FIT_CHROMA), clamp(cb + SKIN_FIT_CHROMA),
        clamp(cr - SKIN_FIT_CHROMA), clamp(cr + SKIN_FIT_CHROMA),
    };
    grid_set_skin(lim);
    report_limits();
}

void grid_frame(uint32_t frame)
{
    if (!streaming && !fit_left)
        return;
    if (!find(frame))
        return;
    if (streaming && uart_host_seen())
        send_line(frame);
    if (fit_left)
        fit_frame(frame);
}
