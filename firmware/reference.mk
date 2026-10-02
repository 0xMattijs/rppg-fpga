# Build Microchip's Hello FPGA video demo firmware with this repo's drivers.
#
#   make -f reference.mk REF=<path to HF10_OV7725_LCD_FF>
#
# Takes main.c, the LCD driver, CMSIS, HAL, and MSS drivers from the
# reference project; takes the camera driver from src/drivers. Writes
# build/reference.hex, which libero/build.tcl loads into eNVM.
# Needs arm-none-eabi-gcc from SoftConsole on PATH.

REF ?= $(HOME)/projects/hello-fpga-ref/HF10_OV7725_LCD_FF
SC  := $(REF)/SC/hellofpga_lcd_cam_ff
OUT := build/reference

SRCS := \
	$(SC)/main.c \
	$(SC)/ili9488.c \
	$(SC)/CMSIS/system_m2sxxx.c \
	$(SC)/CMSIS/startup_gcc/newlib_stubs.c \
	$(SC)/CMSIS/startup_gcc/startup_m2sxxx.S \
	$(SC)/drivers_config/sys_config/sys_config.c \
	$(SC)/drivers/mss_gpio/mss_gpio.c \
	$(SC)/drivers/mss_hpdma/mss_hpdma.c \
	$(SC)/drivers/mss_i2c/mss_i2c.c \
	$(SC)/drivers/mss_nvm/mss_nvm.c \
	$(SC)/drivers/mss_sys_services/mss_comblk.c \
	$(SC)/drivers/mss_sys_services/mss_sys_services.c \
	$(SC)/hal/CortexM3/cortex_nvic.c \
	$(SC)/hal/CortexM3/GNU/hal.S \
	$(SC)/hal/CortexM3/GNU/hw_reg_access.S \
	src/drivers/ov7725.c

# The reference sources include "OV7725.h"; the file is ov7725.h. A copy
# under the include name keeps them building on case-sensitive filesystems.
SHIM := $(OUT)/include/OV7725.h

CFLAGS := -mcpu=cortex-m3 -mthumb -O0 -g -fmessage-length=0 -fsigned-char \
	-ffunction-sections -fdata-sections -std=gnu11 --specs=cmsis.specs \
	-I$(OUT)/include -Isrc/drivers -I$(SC) -I$(SC)/CMSIS -I$(SC)/CMSIS/startup_gcc \
	-I$(SC)/drivers/mss_gpio -I$(SC)/drivers_config -I$(SC)/drivers_config/sys_config \
	-I$(SC)/hal -I$(SC)/hal/CortexM3 -I$(SC)/hal/CortexM3/GNU
LDFLAGS := -T $(SC)/CMSIS/startup_gcc/production-smartfusion2-execute-in-place.ld \
	-Xlinker --gc-sections -Wl,-Map,$(OUT)/reference.map --specs=nano.specs

OBJS := $(patsubst %,$(OUT)/obj/%.o,$(notdir $(SRCS)))
vpath %.c $(sort $(dir $(SRCS)))
vpath %.S $(sort $(dir $(SRCS)))

build/reference.hex: $(OUT)/reference.elf
	arm-none-eabi-objcopy -O ihex $< $@
	arm-none-eabi-size $<

$(OUT)/reference.elf: $(OBJS)
	arm-none-eabi-gcc $(CFLAGS) $(LDFLAGS) -o $@ $^

$(OUT)/obj/%.c.o: %.c $(SHIM) | $(OUT)/obj
	arm-none-eabi-gcc $(CFLAGS) -c -o $@ $<

$(OUT)/obj/%.S.o: %.S | $(OUT)/obj
	arm-none-eabi-gcc $(CFLAGS) -c -o $@ $<

$(SHIM): src/drivers/ov7725.h
	mkdir -p $(dir $@)
	cp $< $@

$(OUT)/obj:
	mkdir -p $@

clean:
	rm -rf $(OUT) build/reference.hex

.PHONY: clean
