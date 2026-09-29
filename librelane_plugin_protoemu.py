# SPDX-License-Identifier: Apache-2.0
"""
LibreLane steps for powering the IHP SRAM on the Tiny Tapeout cmos5l tile.

LibreLane imports every top-level module whose name starts with
``librelane_plugin_``.  The Tiny Tapeout GDS action runs ``python -m librelane``
from the repository root, so this file is picked up without installing it.
``src/config.json`` inserts both steps straight after OpenROAD.GeneratePDN.

See flow/sram_power_columns.py for why the SRAM needs this.
"""
import os

from librelane.steps import Step
from librelane.steps.odb import OdbpyStep
from librelane.steps.openroad import GeneratePDN

FLOW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow")


@Step.factory.register()
class SramPowerColumns(OdbpyStep):
    """Land Metal4 power stripes on the SRAM's supply pins."""

    id = "Project.SramPowerColumns"
    name = "SRAM Power Columns"

    def get_script_path(self):
        return os.path.join(FLOW_DIR, "sram_power_columns.py")


@Step.factory.register()
class RecheckPowerGrid(GeneratePDN):
    """
    Rerun the power grid connectivity check on the finished PDN.

    Subclasses GeneratePDN only to reuse its handling of the check's reports
    (the ``design__power_grid_violation__count`` metric); the script itself
    runs no pdngen.
    """

    id = "Project.RecheckPowerGrid"
    name = "Recheck Power Grid"

    def get_script_path(self):
        return os.path.join(FLOW_DIR, "recheck_power_grid.tcl")
