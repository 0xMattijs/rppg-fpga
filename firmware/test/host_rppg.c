/* Host harness for src/dsp/rppg.c. Reads a session CSV (capture.py format)
 * and pushes every frame, the way main.c does.
 *
 *   host_rppg session.csv [--pulse]
 *
 * Prints one "EST <frame> <bpm_raw> <bpm> <quality>" line per estimate, when
 * rppg_push() says one is due. <frame> is the frame counter of the last sample. With --pulse it then prints
 * the band-passed pulse of the last estimate, one sample per line.
 */
#include <stdio.h>
#include <string.h>
#include "config.h"
#include "rppg.h"

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s session.csv [--pulse]\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "r");
    if (!f) {
        perror(argv[1]);
        return 2;
    }

    char line[256];
    if (!fgets(line, sizeof line, f))   /* header */
        return 2;

    rppg_init();
    unsigned long frame, ts;
    double r, g, b, n;
    int estimates = 0;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%lu,%lu,%lf,%lf,%lf,%lf", &frame, &ts, &r, &g, &b, &n) != 6)
            continue;
        if (n < 1)              /* main.c skips frames with no pixels */
            continue;
        rppg_sample_t s = { (uint32_t)frame, (uint32_t)ts,
                            (float)(r / n), (float)(g / n), (float)(b / n) };
        rppg_result_t res;
        if (rppg_push(&s) && rppg_estimate(&res) == 0) {
            printf("EST %lu %.4f %.4f %.6f\n", frame, res.bpm_raw, res.bpm, res.quality);
            estimates++;
        }
    }
    fclose(f);

    if (!estimates) {
        fprintf(stderr, "not enough frames (need %d)\n", WINDOW_SAMPLES);
        return 1;
    }
    if (argc > 2 && strcmp(argv[2], "--pulse") == 0) {
        const float *p = rppg_debug_pulse();
        for (int i = 0; i < WINDOW_SAMPLES; i++)
            printf("%.9g\n", p[i]);
    }
    return 0;
}
