# Libero SoC project

Keep generated Libero output out of Git. Commit only:

- HDL sources (in `../hdl/src`)
- Constraint files (`*.pdc`, `*.sdc`) in `constraint/`
- A Tcl script that rebuilds the project from scratch (`build.tcl`, to add in Phase 1)

Phase 1: start from Microchip's Hello FPGA camera-to-display reference design,
then add `roi_accumulator` as an APB slave in Phase 2.
