#ifndef CONFIG_H
#define CONFIG_H

#define FRAME_RATE_HZ      30
#define WINDOW_SAMPLES     300   /* 10 s at 30 fps */
#define FFT_SIZE           512
#define HR_MIN_MHZ         700   /* 42 bpm; whole mHz so #if can compare it */
#define HR_MAX_MHZ         4000  /* 240 bpm */
#define HR_MIN_HZ          (HR_MIN_MHZ / 1000.0f)
#define HR_MAX_HZ          (HR_MAX_MHZ / 1000.0f)
#define POS_WINDOW         48    /* ~1.6 s, per Wang et al. 2017 */
#define ESTIMATE_EVERY     30    /* frames between estimates: 1 s at 30 fps */
#define BPM_SMOOTH_ALPHA   0.3f  /* EMA weight of each new estimate; tied to ESTIMATE_EVERY */
#define MAX_GAP_FILL       5     /* longest frame-counter gap filled by interpolation;
                                    a longer gap restarts the window */
#define HARMONIC_RATIO     0.25f /* report half the peak frequency when its power is at
                                    least this fraction of the peak's */

/* Fabric APB base for roi_accumulator; set once the Libero design is fixed. */
#define ROI_ACC_BASE       0x50000000u

#endif
