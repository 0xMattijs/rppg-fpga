#ifndef DUMP_H
#define DUMP_H

#include <stdint.h>

/* eNVM read-back for the PC (tools/rppg/envm_dump.py). The console's
 * "dump [<offset> <length>]" sends eNVM bytes as lines that capture.py
 * ignores, then a summary line:
 *
 *   ENVM <offset> <base64>       offset in hex; up to 48 bytes
 *   ENVM end <length> <crc32>    length in decimal, CRC-32 (zlib's) in hex
 *
 * The whole 256 KB takes about 20 s, during which the main loop stops, so
 * frames are lost and the estimates restart afterwards. */

#define ENVM_BASE 0x60000000u
#define ENVM_SIZE (256u * 1024u)

/* Sends eNVM bytes [offset, offset + length). Returns -1, sending nothing,
 * if the range isn't inside the eNVM. */
int dump_envm(uint32_t offset, uint32_t length);

#endif
