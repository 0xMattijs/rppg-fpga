#ifndef CONFIG_H
#define CONFIG_H

#define FRAME_RATE_HZ      30
#define WINDOW_SAMPLES     300   /* 10 s at 30 fps */
#define FFT_SIZE           512
#define HR_MIN_HZ          0.7f  /* 42 bpm */
#define HR_MAX_HZ          4.0f  /* 240 bpm */
#define POS_WINDOW         48    /* ~1.6 s, per Wang et al. 2017 */
#define ESTIMATE_EVERY     30    /* frames between estimates: 1 s at 30 fps */
#define BPM_SMOOTH_ALPHA   0.3f  /* EMA weight of each new estimate; tied to ESTIMATE_EVERY */

/* Fabric APB base for roi_accumulator; set once the Libero design is fixed. */
#define ROI_ACC_BASE       0x50000000u

#endif
