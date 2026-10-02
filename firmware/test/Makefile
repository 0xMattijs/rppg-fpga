# Host build of the DSP code, for checking it against tools/rppg/pos.py.
# Run the comparison with: python -m rppg.check_firmware (from tools/).

CC      ?= cc
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Werror
CFLAGS  += -DRPPG_HOST -I../include -I../src/dsp

host_rppg: host_rppg.c ../src/dsp/rppg.c ../src/dsp/bandpass_coeffs.h ../include/config.h ../include/rppg.h
	$(CC) $(CFLAGS) -o $@ host_rppg.c ../src/dsp/rppg.c -lm

clean:
	rm -f host_rppg

.PHONY: clean
