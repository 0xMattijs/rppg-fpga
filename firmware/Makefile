# Build the rPPG firmware for the Cortex-M3.
#
#   make REF=<path to HF10_OV7725_LCD_FF>
#
# Writes build/rppg.hex; pass it to libero/build.tcl to load it into eNVM.
# See sf2.mk for what comes from the reference project.

NAME := rppg
OUT  := build/rppg
APP_SRCS = src/main.c
include sf2.mk
