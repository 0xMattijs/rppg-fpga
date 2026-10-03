/* Text commands from the PC; see include/console.h. */
#include <stdint.h>
#include "config.h"
#include "console.h"
#include "dump.h"
#include "grid.h"
#include "ili9488.h"
#include "preview.h"
#include "uart.h"
#include "ui.h"

/* apb3_if's INIT_DONE register (reference Hello_system.h, C_INIT_DONE_ADDR).
 * 1 gives the LCD bus to the fabric's video path, 0 to apb3_if's registers,
 * which write_cmd() and write_data8() drive. */
#define LCD_INIT_DONE (*(volatile uint32_t *)0x30000728u)

#define RX_RING  256     /* power of two */
#define LINE_MAX 96

/* Single producer (SysTick), single consumer (main loop). */
static volatile uint8_t  ring[RX_RING];
static volatile uint32_t ring_head, ring_tail;

static char line[LINE_MAX];
static int  line_len, line_overrun;

void console_rx(void)
{
    int c;
    while ((c = uart_getc()) >= 0) {
        if (ring_head - ring_tail < RX_RING) {
            ring[ring_head % RX_RING] = (uint8_t)c;
            ring_head++;
        }
    }
}

static int is_space(char c)
{
    return c == ' ' || c == '\t';
}

/* Parses the next number in base 10 or 16 from *p. Returns 0 on success. */
static int next_num(const char **p, int base, uint32_t *out)
{
    const char *s = *p;
    while (is_space(*s))
        s++;
    if (!*s)
        return -1;
    uint32_t v = 0;
    int digits = 0;
    for (; *s && !is_space(*s); s++, digits++) {
        char c = *s;
        int d = c >= '0' && c <= '9' ? c - '0'
              : base == 16 && c >= 'a' && c <= 'f' ? c - 'a' + 10
              : base == 16 && c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
        if (d < 0)
            return -1;
        v = v * base + d;
    }
    *p = s;
    *out = v;
    return digits ? 0 : -1;
}

/* Borrows the LCD bus from the video path for one command. The video path
 * starts a new frame at the next VSYNC, so at worst one frame is lost. */
static void lcd_command(uint8_t cmd, const uint8_t *data, int n)
{
    LCD_INIT_DONE = 0;
    write_cmd(cmd);
    for (int i = 0; i < n; i++)
        write_data8(data[i]);
    LCD_INIT_DONE = 1;
}

static void reply(const char *status, const char *what)
{
    if (!uart_host_seen())
        return;
    uart_puts("# ");
    uart_puts(status);
    uart_puts(": ");
    uart_puts(what);
    uart_puts("\r\n");
}

static int starts_with(const char *s, const char *word)
{
    while (*word)
        if (*s++ != *word++)
            return 0;
    return *s == 0 || is_space(*s);
}

static void run(const char *cmd)
{
    const char *p;
    uint32_t v[16];
    int n = 0;

    if (starts_with(cmd, "lcd")) {
        p = cmd + 3;
        while (n < 16 && next_num(&p, 16, &v[n]) == 0 && v[n] <= 0xFF)
            n++;
        while (is_space(*p))
            p++;
        if (n == 0 || *p) {
            reply("error", "lcd <cmd> [<data> ...], at most 15 data bytes, in hex");
            return;
        }
        uint8_t data[15];
        for (int i = 1; i < n; i++)
            data[i - 1] = (uint8_t)v[i];
        lcd_command((uint8_t)v[0], data, n - 1);
    } else if (starts_with(cmd, "test")) {
        p = cmd + 4;
        if (next_num(&p, 10, &v[0]) != 0 || v[0] > 1) {
            reply("error", "test <0|1>");
            return;
        }
        ui_set_test(v[0]);
    } else if (starts_with(cmd, "gain")) {
        p = cmd + 4;
        for (n = 0; n < 3; n++)
            if (next_num(&p, 16, &v[n]) != 0 || v[n] > 0x3FF)
                break;
        if (n < 3) {
            reply("error", "gain <r> <g> <b>, in hex, 80 = 1.0, at most 3ff");
            return;
        }
        ui_set_gain(v[0], v[1], v[2]);
    } else if (starts_with(cmd, "color")) {
        p = cmd + 5;
        for (n = 0; n < 2; n++)
            if (next_num(&p, 16, &v[n]) != 0 || v[n] > 0xFFFF)
                break;
        if (n < 2) {
            reply("error", "color <digit> <wave>, RGB565 in hex");
            return;
        }
        ui_set_colors(v[0], v[1]);
    } else if (starts_with(cmd, "preview")) {
        p = cmd + 7;
        if (next_num(&p, 10, &v[0]) != 0 || v[0] > 1) {
            reply("error", "preview <0|1>");
            return;
        }
        preview_set(v[0]);
    } else if (starts_with(cmd, "grid")) {
        p = cmd + 4;
        if (next_num(&p, 10, &v[0]) != 0 || v[0] > 1) {
            reply("error", "grid <0|1>");
            return;
        }
        grid_stream(v[0]);
    } else if (starts_with(cmd, "mask")) {
        p = cmd + 4;
        if (next_num(&p, 10, &v[0]) != 0 || v[0] > 1) {
            reply("error", "mask <0|1>");
            return;
        }
        grid_set_mask(v[0]);
    } else if (starts_with(cmd, "skin")) {
        p = cmd + 4;
        for (n = 0; n < 6; n++)
            if (next_num(&p, 10, &v[n]) != 0 || v[n] > 255)
                break;
        if (n < 6) {
            reply("error", "skin <y_min> <y_max> <cb_min> <cb_max> <cr_min> <cr_max>, 0..255");
            return;
        }
        uint8_t lim[6];
        for (int i = 0; i < 6; i++)
            lim[i] = (uint8_t)v[i];
        grid_set_skin(lim);
    } else if (starts_with(cmd, "calibrate")) {
        app_calibrate();
    } else if (starts_with(cmd, "restart")) {
        app_restart();
    } else if (starts_with(cmd, "dump")) {
        p = cmd + 4;
        while (n < 2 && next_num(&p, 16, &v[n]) == 0)
            n++;
        while (is_space(*p))
            p++;
        if (n == 0) {
            v[0] = 0;
            v[1] = ENVM_SIZE;
        }
        if (n == 1 || *p || dump_envm(v[0], v[1]) != 0) {
            reply("error", "dump [<offset> <length>], in hex, inside the 256 KB eNVM");
            return;
        }
        /* The main loop stood still for the dump, so frames were lost. */
        app_restart();
    } else if (starts_with(cmd, "roi")) {
        p = cmd + 3;
        for (n = 0; n < 4; n++)
            if (next_num(&p, 10, &v[n]) != 0)
                break;
        if (n < 4 || app_set_roi(v[0], v[1], v[2], v[3]) != 0) {
            reply("error", "roi <x0> <y0> <x1> <y1>, inside 640 x 480");
            return;
        }
    } else {
        reply("error", "unknown command");
        return;
    }
    reply("ok", cmd);
}

void console_poll(void)
{
    while (ring_tail != ring_head) {
        char c = (char)ring[ring_tail % RX_RING];
        ring_tail++;
        /* The PIC32 relays the '&' that a PC tool sends to make sure it is
         * in relay mode; it is not part of any command. */
        if (c == '&')
            continue;
        if (c == '\r' || c == '\n') {
            line[line_len] = 0;
            if (line_overrun)
                reply("error", "line too long");
            else if (line_len)
                run(line);
            line_len = 0;
            line_overrun = 0;
        } else if (line_len < LINE_MAX - 1) {
            line[line_len++] = c;
        } else {
            line_overrun = 1;
        }
    }
}
