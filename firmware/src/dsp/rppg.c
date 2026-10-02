/* rPPG pipeline (Phase 3). Port of tools/rppg/pos.py; keep the two in step.
 *
 * rppg_estimate() runs the whole chain over the last WINDOW_SAMPLES frames:
 * POS with overlap-add, zero-phase band-pass (scipy filtfilt), Hann window,
 * FFT, and the strongest in-band peak. tools/rppg/check_firmware.py builds
 * this file on the PC and compares it against pos.py.
 */
#include <math.h>
#include "rppg.h"
#include "config.h"
#include "bandpass_coeffs.h"

#define PI_F      3.14159265358979f
#define BP_PAD    (3 * BP_TAPS)          /* scipy filtfilt default padlen */
#define FFT_LOG2  9

#if (1 << FFT_LOG2) != FFT_SIZE
#error "FFT_LOG2 does not match FFT_SIZE"
#endif
#if FFT_SIZE < WINDOW_SAMPLES
#error "FFT_SIZE must be at least WINDOW_SAMPLES"
#endif
#if WINDOW_SAMPLES <= BP_PAD
#error "WINDOW_SAMPLES too short for the band-pass padding"
#endif

static rppg_sample_t window[WINDOW_SAMPLES];
static int head, filled;

/* Work buffers, static so the stack stays small. */
static float rgb[WINDOW_SAMPLES][3];
static float pulse[WINDOW_SAMPLES];
static double padded[WINDOW_SAMPLES + 2 * BP_PAD];
static float re[FFT_SIZE], im[FFT_SIZE];
static float cos_tab[FFT_SIZE / 2], sin_tab[FFT_SIZE / 2];

void rppg_init(void)
{
    head = 0;
    filled = 0;
    for (int k = 0; k < FFT_SIZE / 2; k++) {
        cos_tab[k] = cosf(2.0f * PI_F * k / FFT_SIZE);
        sin_tab[k] = sinf(2.0f * PI_F * k / FFT_SIZE);
    }
}

void rppg_push(const rppg_sample_t *s)
{
    window[head] = *s;
    head = (head + 1) % WINDOW_SAMPLES;
    if (filled < WINDOW_SAMPLES)
        filled++;
}

/* POS (Wang et al., 2017): project each temporally normalized POS_WINDOW
 * slice onto the plane orthogonal to skin tone, then overlap-add. */
static void pos(void)
{
    for (int i = 0; i < WINDOW_SAMPLES; i++)
        pulse[i] = 0.0f;

    for (int t = 0; t + POS_WINDOW <= WINDOW_SAMPLES; t++) {
        float mean[3] = {0, 0, 0};
        for (int i = t; i < t + POS_WINDOW; i++)
            for (int c = 0; c < 3; c++)
                mean[c] += rgb[i][c];
        for (int c = 0; c < 3; c++)
            mean[c] /= POS_WINDOW;

        float s1[POS_WINDOW], s2[POS_WINDOW];
        float m1 = 0, m2 = 0;
        for (int i = 0; i < POS_WINDOW; i++) {
            float r = rgb[t + i][0] / mean[0];
            float g = rgb[t + i][1] / mean[1];
            float b = rgb[t + i][2] / mean[2];
            s1[i] = g - b;
            s2[i] = -2.0f * r + g + b;
            m1 += s1[i];
            m2 += s2[i];
        }
        m1 /= POS_WINDOW;
        m2 /= POS_WINDOW;

        float v1 = 0, v2 = 0;
        for (int i = 0; i < POS_WINDOW; i++) {
            v1 += (s1[i] - m1) * (s1[i] - m1);
            v2 += (s2[i] - m2) * (s2[i] - m2);
        }
        float alpha = sqrtf(v1 / POS_WINDOW) / (sqrtf(v2 / POS_WINDOW) + 1e-9f);

        /* p - mean(p) == (s1 - m1) + alpha * (s2 - m2) */
        for (int i = 0; i < POS_WINDOW; i++)
            pulse[t + i] += (s1[i] - m1) + alpha * (s2[i] - m2);
    }
}

/* One pass of a direct form II transposed IIR over x, in place. */
static void iir(double *x, int n, double x0)
{
    double z[BP_TAPS - 1];
    for (int k = 0; k < BP_TAPS - 1; k++)
        z[k] = bp_zi[k] * x0;

    for (int i = 0; i < n; i++) {
        double in = x[i];
        double out = bp_b[0] * in + z[0];
        for (int k = 0; k < BP_TAPS - 2; k++)
            z[k] = bp_b[k + 1] * in + z[k + 1] - bp_a[k + 1] * out;
        z[BP_TAPS - 2] = bp_b[BP_TAPS - 1] * in - bp_a[BP_TAPS - 1] * out;
        x[i] = out;
    }
}

/* Zero-phase band-pass, matching scipy.signal.filtfilt defaults:
 * odd extension by BP_PAD samples, steady-state initial conditions. */
static void bandpass(void)
{
    const int n = WINDOW_SAMPLES, len = n + 2 * BP_PAD;

    for (int i = 0; i < n; i++)
        padded[BP_PAD + i] = pulse[i];
    for (int i = 1; i <= BP_PAD; i++) {
        padded[BP_PAD - i] = 2.0 * pulse[0] - pulse[i];
        padded[BP_PAD + n - 1 + i] = 2.0 * pulse[n - 1] - pulse[n - 1 - i];
    }

    iir(padded, len, padded[0]);
    for (int i = 0; i < len / 2; i++) {
        double t = padded[i];
        padded[i] = padded[len - 1 - i];
        padded[len - 1 - i] = t;
    }
    iir(padded, len, padded[0]);

    /* The second pass ran on reversed data; read it back reversed. */
    for (int i = 0; i < n; i++)
        pulse[i] = (float)padded[len - 1 - BP_PAD - i];
}

/* In-place radix-2 complex FFT of size FFT_SIZE. */
static void fft(void)
{
    for (int i = 1, j = 0; i < FFT_SIZE; i++) {
        int bit = FFT_SIZE >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j |= bit;
        if (i < j) {
            float t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    for (int len = 2; len <= FFT_SIZE; len <<= 1) {
        int step = FFT_SIZE / len;
        for (int i = 0; i < FFT_SIZE; i += len) {
            for (int k = 0; k < len / 2; k++) {
                float wr = cos_tab[k * step], wi = -sin_tab[k * step];
                int a = i + k, b = a + len / 2;
                float tr = re[b] * wr - im[b] * wi;
                float ti = re[b] * wi + im[b] * wr;
                re[b] = re[a] - tr;
                im[b] = im[a] - ti;
                re[a] += tr;
                im[a] += ti;
            }
        }
    }
}

int rppg_estimate(rppg_result_t *out)
{
    if (filled < WINDOW_SAMPLES)
        return -1;

    /* Unroll the ring, oldest first. */
    for (int i = 0; i < WINDOW_SAMPLES; i++) {
        const rppg_sample_t *s = &window[(head + i) % WINDOW_SAMPLES];
        rgb[i][0] = s->r;
        rgb[i][1] = s->g;
        rgb[i][2] = s->b;
    }

    pos();
    bandpass();

    /* Hann window (numpy.hanning), zero-padded to FFT_SIZE. */
    for (int i = 0; i < FFT_SIZE; i++) {
        re[i] = i < WINDOW_SAMPLES
            ? pulse[i] * (0.5f - 0.5f * cosf(2.0f * PI_F * i / (WINDOW_SAMPLES - 1)))
            : 0.0f;
        im[i] = 0.0f;
    }
    fft();

    const float df = (float)FRAME_RATE_HZ / FFT_SIZE;
    int kmin = (int)ceilf(HR_MIN_HZ / df), kmax = (int)floorf(HR_MAX_HZ / df);
    int kbest = kmin;
    float pbest = 0, total = 0;
    for (int k = kmin; k <= kmax; k++) {
        float p = re[k] * re[k] + im[k] * im[k];
        total += p;
        if (p > pbest) {
            pbest = p;
            kbest = k;
        }
    }
    if (total <= 0)
        return -1;

    out->bpm = kbest * df * 60.0f;
    out->quality = pbest / total;
    return 0;
}

#ifdef RPPG_HOST
const float *rppg_debug_pulse(void)
{
    return pulse;
}
#endif
