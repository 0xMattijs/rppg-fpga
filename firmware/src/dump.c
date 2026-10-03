/* eNVM read-back for the PC; see include/dump.h. */
#include <stdint.h>
#include "dump.h"
#include "uart.h"

#define LINE_BYTES 48   /* 64 base64 characters */

/* Bitwise CRC-32 (reflected, polynomial 0xEDB88320), as zlib.crc32
 * computes it; a table would cost 1 KB of RAM for no visible gain. */
static uint32_t crc32_update(uint32_t crc, const uint8_t *p, uint32_t n)
{
    crc = ~crc;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1));
    }
    return ~crc;
}

int dump_envm(uint32_t offset, uint32_t length)
{
    if (offset > ENVM_SIZE || length > ENVM_SIZE - offset)
        return -1;
    const uint8_t *envm = (const uint8_t *)ENVM_BASE;
    uint32_t crc = 0;
    for (uint32_t off = offset; off < offset + length; off += LINE_BYTES) {
        uint32_t n = offset + length - off;
        if (n > LINE_BYTES)
            n = LINE_BYTES;
        uart_puts("ENVM ");
        for (int shift = 28; shift >= 0; shift -= 4)
            uart_putc("0123456789abcdef"[(off >> shift) & 0xF]);
        uart_putc(' ');
        uart_putbase64(envm + off, (int)n);
        uart_puts("\r\n");
        crc = crc32_update(crc, envm + off, n);
    }
    uart_puts("ENVM end ");
    uart_putu(length);
    uart_putc(' ');
    uart_puthex(crc);
    uart_puts("\r\n");
    return 0;
}
