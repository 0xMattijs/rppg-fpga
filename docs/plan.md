# Project plan

The full plan lives in Claude Docs:
[Contactless Heart-Rate Monitor: Project Plan](https://claude.ai/artifact/KwX5ScgzKnqv4AfEsfG2iQ).

## Summary

- **Goal:** live BPM on the touch display, within 5 bpm mean absolute error of
  the M5 heart-rate sensor, seated and still, in steady light.
- **Signal:** 0.7–4 Hz (42–240 bpm) ripple in skin color, strongest in green.
- **Split:** per-pixel work in fabric; per-frame work on the Cortex-M3.

## UART frame format (Phase 2)

The firmware sends one line per frame, at frame end:

```
<frame_counter>,<timestamp_us>,<sum_r>,<sum_g>,<sum_b>,<pixel_count>
```

During validation (Phase 5) it sends one line per second instead:

```
BPM,<timestamp_ms>,<camera_bpm>,<m5_bpm>,<quality>
```

## Open questions

- Camera resolution, pixel format, and register interface (check the kit
  docs before Phase 2).
- M5 heart-rate unit logic levels versus the Hello FPGA headers.
