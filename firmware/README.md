# Cortex-M3 firmware

Build with SoftConsole. Import the SmartFusion2 drivers and CMSIS files that
Libero generates into `drivers/` (not committed until Phase 1 settles them).

| File | Purpose | Phase |
|------|---------|-------|
| `src/main.c` | Frame IRQ, ring buffer, UART output | 2 |
| `src/dsp/rppg.c` | Normalization, POS, band-pass, FFT, peak pick | 3 |
| `src/ui/ui.c` | BPM digits, waveform, quality, ROI drag | 4 |
| `src/drivers/m5_hr.c` | M5 heart-rate unit over I2C | 5 |
