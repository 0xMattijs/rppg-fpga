# Build Microchip's Hello FPGA video demo firmware with this repo's drivers.
#
#   make -f reference.mk REF=<path to HF10_OV7725_LCD_FF>
#
# Takes main.c from the reference project and the rest as sf2.mk describes.
# Writes build/reference.hex, which libero/build.tcl can load into eNVM.

NAME := reference
OUT  := build/reference
APP_SRCS = $(SC)/main.c
include sf2.mk
