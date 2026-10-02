# Rebuild the Hello FPGA video reference design and export programming files.
#
# Usage (after sourcing ~/Microchip/setup-microchip-tools.sh):
#   libero SCRIPT:libero/build.tcl "SCRIPT_ARGS:<ref_project_dir> [<build_dir>]"
#
# <ref_project_dir>  Unpacked HF10_OV7725_LCD_FF project (Libero v12.7). It is
#                    copied, never modified.
# <build_dir>        Where the converted project goes. Default: libero/build,
#                    which Git ignores. Wiped and recreated on every run.
#
# Output: <build_dir>/export/rppg_ref.dat (DirectC, for the Hello FPGA GUI)
# and rppg_ref.stp (STAPL, for FlashPro). Both program fabric and eNVM.

set script_dir [file dirname [file normalize [info script]]]

if {$argc < 1} {
    error "usage: libero SCRIPT:build.tcl \"SCRIPT_ARGS:<ref_project_dir> \[<build_dir>\]\""
}
set ref_dir [file normalize [lindex $argv 0]]
if {$argc >= 2} {
    set build_dir [file normalize [lindex $argv 1]]
} else {
    set build_dir [file join $script_dir build]
}

set prjx_name HF10_OV7725_LCD_FF.prjx
if {![file exists [file join $ref_dir $prjx_name]]} {
    error "no $prjx_name in $ref_dir"
}

# Only wipe a directory this script created, marked by .rppg-build.
set marker [file join $build_dir .rppg-build]
if {[file exists $build_dir]} {
    if {![file exists $marker]} {
        error "$build_dir exists but was not made by build.tcl; remove it yourself"
    }
    file delete -force $build_dir
}
file mkdir [file dirname $build_dir]
file copy $ref_dir $build_dir
close [open $marker w]

set export_dir [file join $build_dir export]
file mkdir $export_dir

# Opening a v12.7 project in a newer Libero converts it in place.
open_project -file [file join $build_dir $prjx_name] \
    -do_backup_on_convert 1 \
    -backup_file [file join $build_dir convert_backup.zip]

run_tool -name {SYNTHESIZE}
run_tool -name {PLACEROUTE}
run_tool -name {VERIFYTIMING}
run_tool -name {GENERATEPROGRAMMINGDATA}

# The eNVM client reads its firmware from a Windows path
# (SC\hellofpga_lcd_cam_ff\Release\hellofpga_lcd_cam_ff.hex). Libero reuses the
# stored eNVM data, so this works until the firmware changes.
configure_tool -name {GENERATEPROGRAMMINGFILE} \
    -params {program_fabric:true} \
    -params {program_security:false} \
    -params {program_envm:true}
run_tool -name {GENERATEPROGRAMMINGFILE}

export_bitstream_file -file_name {rppg_ref} -export_dir $export_dir \
    -format {DAT STP} \
    -trusted_facility_file 1 \
    -trusted_facility_file_components {FABRIC ENVM}

save_project
close_project
puts "build.tcl: programming files in $export_dir"
