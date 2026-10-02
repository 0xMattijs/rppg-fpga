#include <stdint.h>
#include "m2sxxx.h"
#include "system_m2sxxx.h"
#include "config.h"
#include "console.h"
#include "rppg.h"
#include "uart.h"
#include "ui.h"
#include "preview.h"
#include "OV7725.h"
#include "ili9488.h"
#include "drivers/mss_i2c/mss_i2c.h"

/* rppg_top registers (word offsets); see hdl/src/rppg_top.v */
#define REG_SUM_R      0
#define REG_SUM_G      1
#define REG_SUM_B      2
#define REG_COUNT      3
#define REG_FRAME      4
#define REG_TIMESTAMP  5
#define REG_GEOMETRY   6
#define REG_ROI_X      7
#define REG_ROI_Y      8
#define REG_BUTTONS    13

#define FRAME_W        640
#define FRAME_H        480

/* Frames buffered between the SysTick handler and the main loop. An
 * estimate takes a large fraction of a second in soft float, so this must
 * hold more frames than arrive during one estimate. Power of two. */
#define FRAME_QUEUE 64

/* A button counts as pressed or released once it has held still this long. */
#define DEBOUNCE_MS 20

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

/* Button presses, one bit per button (SW1 = bit 0), set by the SysTick
 * handler and cleared by the main loop. */
static volatile uint32_t button_events;

/* Debounces the three push buttons; called every millisecond. */
static void poll_buttons(void)
{
    static uint32_t stable;
    static uint8_t  held[3];
    uint32_t raw = roi[REG_BUTTONS];
    for (int i = 0; i < 3; i++) {
        uint32_t bit = 1u << i;
        if ((raw ^ stable) & bit) {
            if (++held[i] >= DEBOUNCE_MS) {
                stable ^= bit;
                held[i] = 0;
                if (stable & bit)
                    button_events |= bit;
            }
        } else {
            held[i] = 0;
        }
    }
}

/* The fabric latches each frame's sums at VSYNC and holds them for a whole
 * frame (33 ms), and there is no fabric interrupt line, so poll at 1 kHz. */
void SysTick_Handler(void)
{
    poll_buttons();
    console_rx();

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

    /* Here rather than in the main loop, which an estimate blocks for a
     * fifth of a second. */
    ui_frame(f.sum_g, f.count);

    uint32_t h = q_head;
    if (h - q_tail >= FRAME_QUEUE) {
        queue_overflows++;      /* shows up as a frame-counter gap */
        return;
    }
    queue[h % FRAME_QUEUE] = f;
    q_head = h + 1;
}

/* Waits up to 2 ms for the I2C transfer in progress. */
static mss_i2c_status_t i2c_wait(void)
{
    uint32_t start = DWT->CYCCNT;
    mss_i2c_status_t st;
    while ((st = MSS_I2C_get_status(&g_mss_i2c0)) == MSS_I2C_IN_PROGRESS &&
           DWT->CYCCNT - start < SystemCoreClock / 500)
        ;
    return st;
}

/* Reads one camera register: SCCB has no repeated start, so the address
 * goes in its own write. (The driver's ReadReg() skips that write.) Returns
 * -1 if the camera doesn't answer. */
static int cam_read(uint8_t reg)
{
    uint8_t val;
    MSS_I2C_write(&g_mss_i2c0, 0x21, &reg, 1, MSS_I2C_RELEASE_BUS);
    if (i2c_wait() != MSS_I2C_SUCCESS)
        return -1;
    MSS_I2C_read(&g_mss_i2c0, 0x21, &val, 1, MSS_I2C_RELEASE_BUS);
    if (i2c_wait() != MSS_I2C_SUCCESS)
        return -1;
    return val;
}

/* Addresses that answer on the camera's I2C bus, for finding the LCD
 * board's touch controller. Reported in the header line. */
#define I2C_SCAN_MAX 8
static uint8_t i2c_found[I2C_SCAN_MAX];
static int     i2c_found_n;

static void i2c_scan(void)
{
    for (uint8_t a = 0x08; a < 0x78; a++) {
        uint8_t byte;
        MSS_I2C_read(&g_mss_i2c0, a, &byte, 1, MSS_I2C_RELEASE_BUS);
        if (i2c_wait() == MSS_I2C_SUCCESS && i2c_found_n < I2C_SCAN_MAX)
            i2c_found[i2c_found_n++] = a;
    }
}

/* Frames before this one were summed over the previous ROI; the DSP skips
 * them. */
static uint32_t roi_valid_from;

/* Set by the console's "restart"; the main loop restarts the estimates at
 * the next frame and reports it. */
static int restart_requested;

void app_restart(void)
{
    restart_requested = 1;
}

/* Light calibration (SW3, console "calibrate"): the camera's automatic
 * exposure, gain, and white balance run for CAL_SETTLE_MS on the scene in
 * front of it, then lock again, as at power-up (ov7725.c). Frames in
 * between are not used. */
#define COM8_AUTO   0x0F    /* AEC, AWB, AGC on (the reference's setting) */
#define COM8_LOCKED 0x08    /* all three off: the sensor keeps the last values */
static int calibrating;
static uint32_t cal_start;

void app_calibrate(void)
{
    WriteReg(OV7725_COM8, COM8_AUTO);
    cal_start = DWT->CYCCNT;
    calibrating = 1;
}

/* Reports the camera's gain and exposure: with the gain high, row noise
 * swamps the pulse. Exposure is AECH:AEC, in rows. */
static void report_camera(void)
{
    int com8 = cam_read(OV7725_COM8), gain = cam_read(OV7725_GAIN);
    int exposure = cam_read(OV7725_AECH) << 8 | cam_read(OV7725_AEC);
    uart_puts("camera COM8 ");
    uart_puthex(com8);
    uart_puts(" gain ");
    uart_puthex(gain);
    uart_puts(" exposure ");
    uart_puthex(exposure);
}

/* Locks the camera once the calibration has settled; call from the main
 * loop. */
static void poll_calibration(void)
{
    if (!calibrating)
        return;
    uint32_t ms = (DWT->CYCCNT - cal_start) / (SystemCoreClock / 1000);
    if (ms < CAL_SETTLE_MS) {
        ui_show_countdown((CAL_SETTLE_MS - ms + 999) / 1000);   /* 3, 2, 1 */
        return;
    }
    WriteReg(OV7725_COM8, COM8_LOCKED);
    calibrating = 0;
    /* The frame in progress may have been exposed before the lock. */
    roi_valid_from = roi[REG_FRAME] + 2;
#if ENABLE_DSP
    rppg_init();
    ui_show_none();
#endif
    if (uart_host_seen()) {
        uart_puts("# calibrated, ");
        report_camera();
        uart_puts("\r\n");
    }
}

int app_set_roi(int x0, int y0, int x1, int y1)
{
    if (x0 < 0 || y0 < 0 || x1 > FRAME_W || y1 > FRAME_H || x0 >= x1 || y0 >= y1)
        return -1;
    roi[REG_ROI_X] = (uint32_t)x1 << 16 | (uint32_t)x0;
    roi[REG_ROI_Y] = (uint32_t)y1 << 16 | (uint32_t)y0;
    /* The fabric switches at the next VSYNC, so the frame after the one in
     * progress is the first with the new ROI. */
    roi_valid_from = roi[REG_FRAME] + 2;
#if ENABLE_DSP
    rppg_init();
    ui_show_none();
#endif
    if (uart_host_seen()) {
        uart_puts("# roi ");
        uart_putu(x0); uart_putc(' '); uart_putu(y0); uart_putc(' ');
        uart_putu(x1); uart_putc(' '); uart_putu(y1);
        uart_puts("\r\n");
    }
    return 0;
}

/* SW1 steps the ROI through a 3 x 3 grid of positions, starting in the
 * middle; SW2 steps through three sizes; SW3 recalibrates the camera to the
 * light (app_calibrate). The color test pattern is the console's "test". */
static void handle_buttons(void)
{
    static const int16_t pos[9][2] = {
        {320, 240}, {160, 120}, {320, 120}, {480, 120}, {480, 240},
        {480, 360}, {320, 360}, {160, 360}, {160, 240},
    };
    static const int16_t size[3][2] = { {160, 120}, {240, 180}, {96, 72} };
    static int p, s;

    uint32_t ev = button_events;
    if (!ev)
        return;
    button_events &= ~ev;       /* SysTick only sets bits */

    if (ev & 3) {
        if (ev & 1)
            p = (p + 1) % 9;
        if (ev & 2)
            s = (s + 1) % 3;
        int w = size[s][0], h = size[s][1];
        int x0 = pos[p][0] - w / 2, y0 = pos[p][1] - h / 2;
        app_set_roi(x0, y0, x0 + w, y0 + h);
    }
    if (ev & 4)
        app_calibrate();
}

int main(void)
{
    /* The camera first: OV7725_init() settles exposure for 2 s and then
     * locks it. The LCD then switches from its start-up screen to video. */
    OV7725_init();
    ILI9488_init();
    i2c_scan();

    /* The instruction cache in front of the eNVM is off after reset, and
     * every fetch then waits for the eNVM. Turn it on after the start-up
     * delays, which the reference times with busy loops. */
    uint32_t cc_cr_boot = SYSREG->CC_CR, envm_cr_boot = SYSREG->ENVM_CR;
    SYSREG->FLUSH_CR = 1u;              /* invalidate whatever the latches hold */
    SYSREG->CC_CR = cc_cr_boot | 1u;    /* CC_CACHE_ENB */

    ui_init();
    last_seen_frame = roi[REG_FRAME];
    SysTick_Config(SystemCoreClock / 1000);

#if ENABLE_DSP
    rppg_init();
#endif
    int host_seen = 0, header_sent = 0;

    for (;;) {
        handle_buttons();
        console_poll();
        poll_calibration();

        if (q_tail == q_head)
            continue;
        frame_sums_t f = queue[q_tail % FRAME_QUEUE];
        q_tail++;

        /* Until the PIC32 relays, a byte sent to it overruns its UART, which
         * then stops receiving until the board is power-cycled. So the
         * display works from power-on, and the UART waits for the PC. */
        if (!host_seen && uart_host_seen()) {
            host_seen = 1;
            restart_requested = 1;
        }

        if (host_seen) {
            /* One comment line with the camera geometry, the cache registers
             * at boot, and the I2C scan, for checking the setup. capture.py
             * skips lines that don't have six fields. */
            if (!header_sent) {
                uint32_t g = roi[REG_GEOMETRY];
                uart_puts("# lines ");
                uart_putu(g & 0x3FF);
                uart_puts(", pixels per line ");
                uart_putu(g >> 16);
                uart_puts(", CC_CR at boot ");
                uart_puthex(cc_cr_boot);
                uart_puts(", ENVM_CR ");
                uart_puthex(envm_cr_boot);
                uart_puts(", ");
                report_camera();
                uart_puts(", I2C");
                for (int i = 0; i < i2c_found_n; i++) {
                    uart_putc(' ');
                    uart_puthex(i2c_found[i]);
                }
                uart_puts("\r\n");
                header_sent = 1;
            }

            /* Restart the estimates at this frame, so the PC can repeat them
             * from a recording that starts here (rppg.check_board). */
            if (restart_requested) {
                restart_requested = 0;
#if ENABLE_DSP
                rppg_init();
                ui_show_none();
#endif
                uart_puts("# restart ");
                uart_putu(f.frame);
                uart_puts("\r\n");
            }

            /* frame,timestamp_us,sum_r,sum_g,sum_b,pixel_count (docs/plan.md) */
            uart_putu(f.frame);         uart_putc(',');
            uart_putu(f.timestamp_us);  uart_putc(',');
            uart_putu(f.sum_r);         uart_putc(',');
            uart_putu(f.sum_g);         uart_putc(',');
            uart_putu(f.sum_b);         uart_putc(',');
            uart_putu(f.count);
            uart_puts("\r\n");
            preview_poll();
        }

#if ENABLE_DSP
        if (f.count == 0 || calibrating || (int32_t)(f.frame - roi_valid_from) < 0)
            continue;
        rppg_sample_t s;
        rppg_result_t res;
        s.frame = f.frame;
        s.timestamp_us = f.timestamp_us;
        s.r = (float)f.sum_r / f.count;
        s.g = (float)f.sum_g / f.count;
        s.b = (float)f.sum_b / f.count;
        if (!rppg_push(&s))
            continue;
        uint32_t start = DWT->CYCCNT;
        if (rppg_estimate(&res) != 0)
            continue;
        uint32_t us = (DWT->CYCCNT - start) / (SystemCoreClock / 1000000u);
        ui_show_bpm(res.bpm, res.quality);
        if (!host_seen)
            continue;

        /* EST <frame> <bpm_raw> <bpm> <quality> <estimate_us>: the format
         * of firmware/test/host_rppg, plus the time the estimate took. */
        uart_puts("EST ");
        uart_putu(f.frame);         uart_putc(' ');
        uart_putf(res.bpm_raw, 2);  uart_putc(' ');
        uart_putf(res.bpm, 2);      uart_putc(' ');
        uart_putf(res.quality, 4);  uart_putc(' ');
        uart_putu(us);
        uart_puts("\r\n");
#endif
    }
}
