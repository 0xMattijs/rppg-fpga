/* Display overlay (Phase 4): BPM digits, quality bar, and scrolling
 * waveform. The fabric draws them (hdl/src/overlay.v); this file only
 * writes its registers. */
#include <stdint.h>
#include "config.h"
#include "ui.h"

/* rppg_top registers (word offsets); see hdl/src/rppg_top.v */
#define REG_OVL_CTRL    10
#define REG_OVL_DIGITS  11
#define REG_OVL_BAR     12
#define REG_COLOR_GAIN  15
#define REG_OVL_COLOR   16
#define REG_WAVE        (0x400 / 4)   /* one word per column */
#define OVL_ON          (1u << 0)
#define OVL_MIRROR      (1u << 1)
#define OVL_TEST        (1u << 2)

#define WAVE_COLS  160
#define WAVE_ROWS  80
#define BAR_PIXELS 200

#define RGB565_RED    0xF800u
#define RGB565_GREEN  0x07E0u

static volatile uint32_t *const regs = (volatile uint32_t *)ROI_ACC_BASE;

/* gfedcba */
static const uint8_t seg7[10] = {
    0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F
};
#define SEG_DASH 0x40

/* Waveform state, touched only from the SysTick handler. */
static float hist[WAVE_COLS];   /* ring, oldest at hist_head */
static int   hist_head;
static float base, smooth, amp;
static int   primed;

static void set_digits(uint32_t d0, uint32_t d1, uint32_t d2)
{
    regs[REG_OVL_DIGITS] = d0 | d1 << 7 | d2 << 14;
}

void ui_show_none(void)
{
    set_digits(SEG_DASH, SEG_DASH, SEG_DASH);
    regs[REG_OVL_BAR] = 0;
}

void ui_show_bpm(float bpm, float quality)
{
    int n = (int)(bpm + 0.5f);
    if (n < 0)
        n = 0;
    if (n > 999)
        n = 999;
    /* Right-aligned, with no leading zeros. */
    set_digits(n >= 100 ? seg7[n / 100] : 0,
               n >= 10 ? seg7[n / 10 % 10] : 0,
               seg7[n % 10]);

    int len = (int)(quality * (BAR_PIXELS / QUALITY_FULL) + 0.5f);
    if (len < 0)
        len = 0;
    if (len > BAR_PIXELS)
        len = BAR_PIXELS;
    uint32_t color = quality < QUALITY_LOW ? RGB565_RED
                   : quality < QUALITY_GOOD ? UI_YELLOW : RGB565_GREEN;
    regs[REG_OVL_BAR] = color << 16 | (uint32_t)len;
}

void ui_set_gain(uint32_t r, uint32_t g, uint32_t b)
{
    regs[REG_COLOR_GAIN] = (b & 0x3FF) << 20 | (g & 0x3FF) << 10 | (r & 0x3FF);
}

void ui_set_colors(uint32_t digit, uint32_t wave)
{
    regs[REG_OVL_COLOR] = (wave & 0xFFFF) << 16 | (digit & 0xFFFF);
}

void ui_init(void)
{
    ui_set_gain(LCD_GAIN_R, LCD_GAIN_G, LCD_GAIN_B);
    ui_set_colors(UI_DIGIT_COLOR, UI_WAVE_COLOR);
    for (int c = 0; c < WAVE_COLS; c++)
        regs[REG_WAVE + c] = 1;          /* first row 1, last row 0: empty */
    ui_show_none();
    regs[REG_OVL_CTRL] = OVL_ON | (UI_MIRROR ? OVL_MIRROR : 0);
}

void ui_set_test(int on)
{
    uint32_t ctrl = regs[REG_OVL_CTRL];
    regs[REG_OVL_CTRL] = on ? ctrl | OVL_TEST : ctrl & ~OVL_TEST;
}

int ui_test(void)
{
    return (regs[REG_OVL_CTRL] & OVL_TEST) != 0;
}

/* Draws the history as a line, oldest on the left. Each column spans the
 * rows between its sample and the previous one, at least 3 rows, since the
 * LCD drops every third line. */
static void draw_wave(void)
{
    float scale = (WAVE_ROWS / 2 - 4) / amp;
    int prev = -1;
    for (int c = 0; c < WAVE_COLS; c++) {
        float v = hist[(hist_head + c) % WAVE_COLS];
        int row = WAVE_ROWS / 2 - (int)(v * scale);
        if (row < 0)
            row = 0;
        if (row > WAVE_ROWS - 1)
            row = WAVE_ROWS - 1;
        if (prev < 0)
            prev = row;
        int lo = row < prev ? row : prev;
        int hi = row < prev ? prev : row;
        if (hi - lo < 2) {
            hi = lo + 2;
            if (hi > WAVE_ROWS - 1) {
                hi = WAVE_ROWS - 1;
                lo = hi - 2;
            }
        }
        regs[REG_WAVE + c] = (uint32_t)hi << 7 | (uint32_t)lo;
        prev = row;
    }
}

void ui_frame(uint32_t sum_g, uint32_t count)
{
    if (count == 0)
        return;
    float g = (float)sum_g / count;
    if (!primed) {
        base = g;
        primed = 1;
    }
    /* High-pass by subtracting a slow average, then smooth a little. Blood
     * absorbs green, so a beat lowers it: flip the sign so beats point up. */
    base += WAVE_HP_ALPHA * (g - base);
    float v = (base - g) / base;
    smooth += 0.5f * (v - smooth);

    hist[hist_head] = smooth;
    hist_head = (hist_head + 1) % WAVE_COLS;

    /* Autoscale to a peak that decays by half in about 2 s. */
    float a = smooth < 0 ? -smooth : smooth;
    amp *= 0.99f;
    if (a > amp)
        amp = a;
    if (amp < WAVE_MIN_AMP)
        amp = WAVE_MIN_AMP;
    draw_wave();
}
