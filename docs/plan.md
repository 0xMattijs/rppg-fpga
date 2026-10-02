# Project plan

The full plan lives in Claude Docs:
[Contactless Heart-Rate Monitor: Project Plan](https://claude.ai/artifact/KwX5ScgzKnqv4AfEsfG2iQ).

## Summary

- **Goal:** live BPM on the touch display, within 5 bpm mean absolute error of
  a reference heart rate (an Apple Watch; the plan named an M5 heart-rate
  unit), seated and still, in steady light.
- **Signal:** 0.7–4 Hz (42–240 bpm) ripple in skin color, strongest in green.
- **Split:** per-pixel work in fabric; per-frame work on the Cortex-M3.

## UART frame format (Phase 2)

The firmware sends one line per frame, at frame end, through the PIC32 to
`/dev/ttyACM0`. `tools/rppg/capture.py` first puts the PIC32 in relay mode;
see its docstring.

```
<frame_counter>,<timestamp_us>,<sum_r>,<sum_g>,<sum_b>,<pixel_count>
```

Before the first frame it sends one comment line, starting with `#`, with
the camera geometry and the cache registers at boot.

After each BPM estimate (Phase 3), once a second, it also sends the
format of `firmware/test/host_rppg` plus the time the estimate took.
`capture.py` writes these lines to a `.est` file next to the CSV.

```
EST <frame_counter> <bpm_this_window> <bpm_smoothed> <quality> <estimate_us>
```

The PC can send text commands back, one per line (Phase 4; see
`firmware/include/console.h` and `tools/rppg/send.py`). The board answers
each with a comment line, `# ok: <command>` or `# error: <usage>`, and
reports an ROI change as `# roi <x0> <y0> <x1> <y1>`. After `restart`, it
restarts the estimates and reports the first frame of the new run as
`# restart <frame>`; `capture.py` sends `restart` and records from that
frame on.

`capture.py` adds one field to each EST line in the `.est` file: the PC's
clock in Unix seconds at the end of the estimate's window. `rppg.validate`
matches that against the reference heart rate (Phase 5).

## Open questions

- Real camera frame rate: 30.01 fps by the fabric's own clock, but all clocks
  come from the on-chip RC oscillator. Check it against the PC clock. See
  [camera-bus.md](camera-bus.md).
- How far the Apple Watch's heart rate lags the true one. `rppg.validate`
  prints the error at each lag from 0 to 15 s.
