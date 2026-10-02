/* Camera preview for the PC; see include/preview.h. */
#include <stdint.h>
#include "config.h"
#include "grid.h"
#include "preview.h"
#include "uart.h"

/* rppg_top registers (word offsets); see hdl/src/rppg_top.v */
#define REG_ROI_X       7
#define REG_ROI_Y       8
#define REG_THUMB_CTRL  17
#define REG_THUMB_DATA  18
#define THUMB_ARM       (1u << 0)
#define THUMB_READY     (1u << 0)

#define THUMB_W 80
#define THUMB_H 60

/* Two rows (2 x 226 bytes) per frame keep the UART at about 14 kB/s of its
 * 23 kB/s, so an image every second, and block the main loop for about
 * 20 ms a frame. GRID lines take another 7 kB/s, so with them on, one row:
 * an image every 2 s. */
#define ROWS_PER_FRAME 2

static volatile uint32_t *const regs = (volatile uint32_t *)ROI_ACC_BASE;
static int on, row = -1;        /* row < 0: waiting for a capture */

static void arm(void)
{
    regs[REG_THUMB_CTRL] = THUMB_ARM;
    row = -1;
}

void preview_set(int v)
{
    on = v;
    if (on)
        arm();
}

void preview_poll(void)
{
    if (!on)
        return;
    if (row < 0) {
        if (!(regs[REG_THUMB_CTRL] & THUMB_READY))
            return;
        uint32_t rx = regs[REG_ROI_X], ry = regs[REG_ROI_Y];
        uart_puts("IMG roi ");
        uart_putu(rx & 0xFFFF); uart_putc(' ');
        uart_putu(ry & 0xFFFF); uart_putc(' ');
        uart_putu(rx >> 16);    uart_putc(' ');
        uart_putu(ry >> 16);
        uart_puts("\r\n");
        row = 0;
    }
    int rows = grid_streaming() ? 1 : ROWS_PER_FRAME;
    for (int n = 0; n < rows && row < THUMB_H; n++, row++) {
        uint8_t buf[2 * THUMB_W];
        for (int x = 0; x < THUMB_W; x++) {
            uint32_t p = regs[REG_THUMB_DATA];
            buf[2 * x] = (uint8_t)(p >> 8);
            buf[2 * x + 1] = (uint8_t)p;
        }
        uart_puts("IMG ");
        uart_putu(row);
        uart_putc(' ');
        uart_putbase64(buf, sizeof buf);
        uart_puts("\r\n");
    }
    if (row >= THUMB_H)
        arm();
}
