# Build the rPPG firmware for the Cortex-M3.
#
#   make REF=<path to HF10_OV7725_LCD_FF>
#
# Writes build/rppg.hex; pass it to libero/build.tcl to load it into eNVM.
# See sf2.mk for what comes from the reference project.

NAME := rppg
OUT  := build/rppg
APP_SRCS = src/main.c src/uart.c src/console.c src/preview.c src/dsp/rppg.c src/ui/ui.c
include sf2.mk

# An estimate must finish within ESTIMATE_EVERY frames (1 s); at -O0 it
# takes 1.04 s and the frame queue overflows. The rest stays at -O0.
$(call obj,src/dsp/rppg.c): CFLAGS += -O2
