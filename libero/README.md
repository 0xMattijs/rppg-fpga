# Libero SoC project

Keep generated Libero output out of Git. Commit only:

- HDL sources (in `../hdl/src`)
- Constraint files (`*.pdc`, `*.sdc`) in `constraint/`
- `build.tcl`, which rebuilds the project from the reference design

## Reference design

The build starts from Microchip's Hello FPGA video demo, `HF10_OV7725_LCD_FF`
(Libero v12.7, M2S010 VF256 -1). Microchip no longer hosts it; an unmodified
copy is in [zhouxinyu0723/Hello_fpga_green_crosses](https://github.com/zhouxinyu0723/Hello_fpga_green_crosses)
as `HF10_OV7725_LCD_FF.7z`. Unpack it outside this repository.

## Build

```bash
source ~/Microchip/setup-microchip-tools.sh
make -C firmware -f reference.mk
libero SCRIPT:libero/build.tcl "SCRIPT_ARGS:$HOME/projects/hello-fpga-ref/HF10_OV7725_LCD_FF $PWD/firmware/build/reference.hex"
```

`firmware/reference.mk` builds Microchip's demo firmware with this repo's
camera driver (`firmware/src/drivers/ov7725.c`). Pass `-` instead of the
`.hex` path to keep Microchip's original firmware image.

The script copies the reference project to `libero/build/`, converts it to the
installed Libero version, runs synthesis, place-and-route, and timing, and
writes `libero/build/export/rppg_ref.dat` (DirectC) and `rppg_ref.stp`
(STAPL). Both program fabric and eNVM. Each run wipes `libero/build/` first.

Phase 2 adds `roi_accumulator` as an APB target on FIC_0.
