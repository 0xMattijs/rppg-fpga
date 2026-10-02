/* Host harness for src/dsp/rppg.c. Reads a session CSV (capture.py format),
 * pushes every frame, and prints the estimate for the final window.
 *
 *   host_rppg session.csv [--pulse]
 *
 * Output: "BPM <bpm> <quality>", then with --pulse one pulse sample per line.
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
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%lu,%lu,%lf,%lf,%lf,%lf", &frame, &ts, &r, &g, &b, &n) != 6)
            continue;
        if (n < 1)
            n = 1;
        rppg_sample_t s = { (uint32_t)frame, (uint32_t)ts,
                            (float)(r / n), (float)(g / n), (float)(b / n) };
        rppg_push(&s);
    }
    fclose(f);

    rppg_result_t res;
    if (rppg_estimate(&res) != 0) {
        fprintf(stderr, "not enough frames (need %d)\n", WINDOW_SAMPLES);
        return 1;
    }
    printf("BPM %.4f %.6f\n", res.bpm, res.quality);

    if (argc > 2 && strcmp(argv[2], "--pulse") == 0) {
        const float *p = rppg_debug_pulse();
        for (int i = 0; i < WINDOW_SAMPLES; i++)
            printf("%.9g\n", p[i]);
    }
    return 0;
}
