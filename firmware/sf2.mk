# Shared SmartFusion2 build settings, included by Makefile and reference.mk.
# Takes CMSIS, HAL, the MSS drivers, and the LCD driver from Microchip's
# reference project. The including file sets NAME, OUT, and APP_SRCS
# (with "=", since APP_SRCS may use $(SC)).
# Needs arm-none-eabi-gcc from SoftConsole on PATH.

# By default, the copy of the reference project that libero/build.tcl makes,
# so the firmware builds without a separate unpacked reference. The sources
# used here are the same in both: the Libero conversion leaves SC/ alone.
REF ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../libero/build)
SC  := $(REF)/SC/hellofpga_lcd_cam_ff
ifeq ($(wildcard $(SC)),)
$(error no reference sources in $(SC); run libero/build.tcl first, or pass REF=<path to HF10_OV7725_LCD_FF>)
endif

SF2_SRCS := \
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

SRCS := $(APP_SRCS) $(SF2_SRCS)

# The reference sources include "OV7725.h"; the file is ov7725.h. A copy
# under the include name keeps them building on case-sensitive filesystems.
SHIM := $(OUT)/include/OV7725.h

CFLAGS := -mcpu=cortex-m3 -mthumb -O0 -g -fmessage-length=0 -fsigned-char \
	-ffunction-sections -fdata-sections -std=gnu11 --specs=cmsis.specs -MMD -MP \
	-Iinclude -I$(OUT)/include -Isrc/drivers -I$(SC) -I$(SC)/CMSIS -I$(SC)/CMSIS/startup_gcc \
	-I$(SC)/drivers/mss_gpio -I$(SC)/drivers_config -I$(SC)/drivers_config/sys_config \
	-I$(SC)/hal -I$(SC)/hal/CortexM3 -I$(SC)/hal/CortexM3/GNU
LDFLAGS := -T $(SC)/CMSIS/startup_gcc/production-smartfusion2-execute-in-place.ld \
	-Xlinker --gc-sections -Wl,-Map,$(OUT)/$(NAME).map --specs=nano.specs

.DEFAULT_GOAL := build/$(NAME).hex

# One explicit rule per source. A vpath search would find the reference
# project's own ov7725.c before src/drivers/ov7725.c.
obj = $(OUT)/obj/$(notdir $(1)).o
OBJS := $(foreach s,$(SRCS),$(call obj,$(s)))
define compile
$(call obj,$(1)): $(1) $(SHIM) | $(OUT)/obj
	arm-none-eabi-gcc $$(CFLAGS) -c -o $$@ $$<
endef
$(foreach s,$(SRCS),$(eval $(call compile,$(s))))
-include $(OBJS:.o=.d)

build/$(NAME).hex: $(OUT)/$(NAME).elf
	arm-none-eabi-objcopy -O ihex $< $@
	arm-none-eabi-size $<

$(OUT)/$(NAME).elf: $(OBJS)
	arm-none-eabi-gcc $(CFLAGS) $(LDFLAGS) -o $@ $^

$(SHIM): src/drivers/ov7725.h
	mkdir -p $(dir $@)
	cp $< $@

$(OUT)/obj:
	mkdir -p $@

clean:
	rm -rf $(OUT) build/$(NAME).hex

.PHONY: clean
