# SPDX-License-Identifier: Apache-2.0
#
# Rerun OpenROAD's power grid check after Project.SramPowerColumns.
#
# OpenROAD.GeneratePDN checks the grid right after pdngen, before the SRAM's
# supply pins have been connected, so its violation count is stale.  This
# repeats exactly the check at the end of LibreLane's pdn.tcl on the updated
# layout, so Checker.PowerGridViolations judges the grid that is taped out.

source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
source $::env(SCRIPTS_DIR)/openroad/common/set_power_nets.tcl

foreach {net} "$::env(VDD_NETS) $::env(GND_NETS)" {
    set report_file $::env(STEP_DIR)/$net-grid-errors.rpt
    set f [open $report_file "w"]
    puts $f ""
    close $f
    if { [catch {check_power_grid -net $net -error_file $report_file} err] } {
        puts stderr "\[WARNING\] Grid check for $net failed: $err"
    }
}

write_views
