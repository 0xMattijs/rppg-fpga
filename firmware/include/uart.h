#ifndef UART_H
#define UART_H

#include <stdint.h>

/* UART to the PC through the PIC32 (rppg_top's uart_tx and uart_rx). Only
 * send once uart_host_seen() is true: a byte that reaches the PIC32 before
 * the PC has put it in relay mode jams its receiver until a power cycle. */

int  uart_host_seen(void);
void uart_putc(char c);
void uart_puts(const char *s);
void uart_putu(uint32_t v);
void uart_puthex(uint32_t v);
/* A non-negative float with a fixed number of decimals (at most 6). */
void uart_putf(float v, int decimals);
/* n bytes in base64, with padding. */
void uart_putbase64(const uint8_t *p, int n);
/* The oldest byte from the PC, or -1 if none. */
int  uart_getc(void);

#endif
