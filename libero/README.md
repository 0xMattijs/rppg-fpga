# Libero SoC project

Keep generated Libero output out of Git. Commit only:

- HDL sources (in `../hdl/src`)
- Constraint files (`*.pdc`, `*.sdc`) in `constraint/`
- `build.tcl`, which rebuilds the project from the reference design
- `rppg_top.tcl`, which `build.tcl` runs to wire `hdl/src/rppg_top.v` into it

## Reference design

The build starts from Microchip's Hello FPGA video demo, `HF10_OV7725_LCD_FF`
(Libero v12.7, M2S010 VF256 -1). Microchip no longer hosts it; an unmodified
copy is in [zhouxinyu0723/Hello_fpga_green_crosses](https://github.com/zhouxinyu0723/Hello_fpga_green_crosses)
as `HF10_OV7725_LCD_FF.7z`. Unpack it outside this repository, for example to
`~/hf10-ref`.

After a build, `libero/build/convert_backup.zip` holds the project as Libero
found it before converting it, so you can recover the reference from there.
Do it before the next build, which deletes `libero/build/`:

```bash
mkdir -p ~/hf10-ref
unzip -q libero/build/convert_backup.zip -d ~/hf10-ref
mv ~/hf10-ref/build ~/hf10-ref/HF10_OV7725_LCD_FF
rm ~/hf10-ref/HF10_OV7725_LCD_FF/.rppg-build
```

## Build

```bash
source ~/Microchip/setup-microchip-tools.sh
export REF=~/hf10-ref/HF10_OV7725_LCD_FF    # the unpacked reference project
make -C firmware
libero SCRIPT:libero/build.tcl "SCRIPT_ARGS:$REF $PWD/firmware/build/rppg.hex"
```

`make -C firmware` builds this repo's firmware. `make -C firmware -f
reference.mk` builds Microchip's demo firmware instead, with this repo's
camera driver. Pass `-` instead of the `.hex` path to keep Microchip's
original firmware image.

`make` reads `REF` from the environment. Without it, the firmware build takes
the reference sources from `libero/build/`, the copy that the last Libero build
left there. `build.tcl` always needs the unpacked reference, because it
deletes `libero/build/` before copying the reference in.

The script copies the reference project to `libero/build/`, converts it to the
installed Libero version, runs synthesis, place-and-route, and timing, and
writes `libero/build/export/rppg.dat` (DirectC) and `rppg.stp` (STAPL).
Both program fabric and eNVM. Each run wipes `libero/build/` first. A build
takes about 2.5 minutes.

It also writes `rppg_fabric.dat`, which programs only the fabric and leaves
the eNVM as it is. Use it to put the design back after something replaced
only the fabric, such as hellofpga-prog's eNVM dumper. The full `rppg.dat`
would also overwrite the firmware with whatever build it was made from.

## Changes to the reference design

`rppg_top.tcl` edits the TOP SmartDesign:

- The camera pins feed `RPPG_0`, which passes them on to `line_write_read_0`
  three flops later, with a green border drawn around the ROI and the
  display overlay (`hdl/src/overlay.v`: BPM digits, quality bar, waveform)
  drawn on top.
- `RPPG_0` is an APB target at 0x30001000 on the FIC_0 bus. The reference
  joined the bus to `apb3_if_0` with one bus-interface net; the script
  replaces it with plain nets and gates `apb3_if_0`'s PSEL.
- `RPPG_0` drives the TX pin to the PIC32 and receives on the RX pin.
- The push buttons SW1, SW2, and SW3 come in on new top-level ports
  `SW1_N`, `SW2_N`, and `SW3_N`: pins K1, J2, and L1, LVCMOS15 (bank 5 runs
  at 1.5 V). The script appends their constraints to the project's copy of
  `user.pdc`.

There is no frame interrupt. The MSS fabric interrupts and GPIO_0 sit inside
the `FlashFreeze_SB` System Builder block, and regenerating it needs the FCCC
2.0.201 core, which Libero 2026.1's vault doesn't have. The firmware polls the
frame counter at 1 kHz instead.
