#ifndef CONSOLE_H
#define CONSOLE_H

/* Text commands from the PC, one per line (tools/rppg/send.py):
 *
 *   lcd <cmd> [<data> ...]   send an ILI9488 command, all bytes in hex
 *   test <0|1>               color test pattern off or on
 *   gain <r> <g> <b>         LCD color gains in hex, 80 = 1.0, up to 3ff
 *   color <digit> <wave>     digit and waveform colors, RGB565 in hex
 *   roi <x0> <y0> <x1> <y1>  move the ROI, in camera pixels (x1, y1 exclusive)
 *   preview <0|1>            camera preview for the PC off or on (preview.h)
 *   restart                  restart the estimates at the next frame, which
 *                            the board reports as "# restart <frame>"
 *
 * Each command answers with a "# ok" or "# error" comment line. */

/* Moves bytes from the fabric's receive FIFO to the line buffer. Call from
 * the SysTick handler, so the FIFO never fills while an estimate runs. */
void console_rx(void);
/* Runs any complete command lines. Call from the main loop. */
void console_poll(void);

/* Implemented in main.c. Returns 0, or -1 if the box doesn't fit the frame. */
int app_set_roi(int x0, int y0, int x1, int y1);
void app_restart(void);

#endif
