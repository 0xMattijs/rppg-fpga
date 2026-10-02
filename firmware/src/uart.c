/* UART through rppg_top; see include/uart.h. */
#include <stdint.h>
#include "config.h"
#include "uart.h"

/* rppg_top registers (word offsets); see hdl/src/rppg_top.v */
#define REG_UART       9
#define REG_UART_RX    14
#define UART_BUSY      (1u << 0)
#define UART_HOST_SEEN (1u << 1)   /* the PC has put the PIC32 in relay mode */
#define RX_VALID       (1u << 8)

static volatile uint32_t *const regs = (volatile uint32_t *)ROI_ACC_BASE;

int uart_host_seen(void)
{
    return (regs[REG_UART] & UART_HOST_SEEN) != 0;
}

void uart_putc(char c)
{
    while (regs[REG_UART] & UART_BUSY)
        ;
    regs[REG_UART] = (uint8_t)c;
}

void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

void uart_putu(uint32_t v)
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

void uart_puthex(uint32_t v)
{
    uart_puts("0x");
    for (int shift = 28; shift >= 0; shift -= 4)
        uart_putc("0123456789abcdef"[(v >> shift) & 0xF]);
}

/* Saves linking printf's float support. */
void uart_putf(float v, int decimals)
{
    uint32_t scale = 1;
    for (int i = 0; i < decimals; i++)
        scale *= 10;
    uint32_t fixed = (uint32_t)(v * scale + 0.5f);
    uart_putu(fixed / scale);
    if (!decimals)
        return;
    uart_putc('.');
    uint32_t frac = fixed % scale;
    for (scale /= 10; scale; scale /= 10) {
        uart_putc('0' + frac / scale);
        frac %= scale;
    }
}

int uart_getc(void)
{
    uint32_t r = regs[REG_UART_RX];     /* reading a valid byte removes it */
    return (r & RX_VALID) ? (int)(r & 0xFF) : -1;
}

static const char b64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

void uart_putbase64(const uint8_t *p, int n)
{
    for (int i = 0; i < n; i += 3) {
        uint32_t v = (uint32_t)p[i] << 16;
        if (i + 1 < n) v |= (uint32_t)p[i + 1] << 8;
        if (i + 2 < n) v |= p[i + 2];
        uart_putc(b64[v >> 18 & 63]);
        uart_putc(b64[v >> 12 & 63]);
        uart_putc(i + 1 < n ? b64[v >> 6 & 63] : '=');
        uart_putc(i + 2 < n ? b64[v & 63] : '=');
    }
}
