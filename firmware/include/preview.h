#ifndef PREVIEW_H
#define PREVIEW_H

/* Camera preview for the PC (tools/rppg/preview.py). While on, the fabric
 * captures an 80 x 60 thumbnail (hdl/src/thumb.v) and the firmware sends it
 * a few rows per frame, as lines that capture.py ignores:
 *
 *   IMG roi <x0> <y0> <x1> <y1>   before each image: the ROI, camera pixels
 *   IMG <row> <base64>            row 0..59: 80 pixels, RGB565, high byte first
 */

void preview_set(int on);
/* Sends the next rows, if any. Call from the main loop once per frame, and
 * only once the PC has been seen. */
void preview_poll(void);

#endif
