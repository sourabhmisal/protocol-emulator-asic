# SPDX-License-Identifier: Apache-2.0
#
# Power the IHP SRAM macro on the Tiny Tapeout sg13cmos5l tile.
#
# Why this exists
# ---------------
# A cmos5l tile has a single-layer PDN: vertical Metal4 stripes plus Metal1
# follow-pin rails.  TopMetal1 is reserved for the Tiny Tapeout top level (the
# precheck rejects it), so there is no horizontal strap layer to drop vias
# onto a macro from above, which is how the SRAM is powered on sg13g2.
#
# The SRAM's supply pins are vertical Metal4 columns, and it obstructs
# Metal1-Metal3 over its whole footprint.  pdngen therefore trims its stripes
# around the macro and nothing reaches the SRAM's supply pins.
#
# What it does
# ------------
# Runs after OpenROAD.GeneratePDN, on the power nets the macro's supply pins
# are connected to (PDN_MACRO_CONNECTIONS):
#
#   1. Deletes every tile stripe that pdngen trimmed (anything shorter than
#      the full stripe height) or that crosses the macro, along with its
#      rail vias and pin shapes.  A trimmed stripe must go either way: the
#      TT precheck rejects power pins that stop short of either tile edge.
#   2. Draws one Metal4 stripe on each of the macro's declared Metal4 supply
#      PIN rectangles.  Inside the macro the stripe is exactly the pin, so
#      no new metal is ever drawn over the macro's obstructions.  Outside, it
#      runs straight to the edge(s) of the core that the pin touches:
#        - pins spanning the full macro height become full-height stripes,
#          and get pin shapes like every other tile stripe;
#        - pins touching only one macro edge (the VDD / VDDARRAY columns,
#          split by a keep-out bar) run to that core edge only, and are fed
#          through the rails, since they cannot be tile power pins.
#   3. Drops the same Metal1->Metal4 via stack pdngen uses onto every rail
#      the new stripes cross outside the macro.
#
# Only declared PIN geometry is used; nothing is inferred from gaps in the
# obstructions.  Signoff is LVS plus Project.RecheckPowerGrid, which reruns
# OpenROAD's power grid check on the result.

import click
import odb

from reader import click_odb


def is_vertical(box):
    return (box.yMax() - box.yMin()) > (box.xMax() - box.xMin())


def x_overlaps(box, x0, x1):
    return box.xMax() > x0 and box.xMin() < x1


def centre(lo, hi):
    return (lo + hi) // 2


@click.command()
@click.option("--layer", "layer_name", default="Metal4", help="PDN stripe layer")
@click.option("--rail-layer", "rail_layer_name", default="Metal1", help="Follow-pin rail layer")
@click.option(
    "--macro-prefix",
    "macro_prefix",
    default="RM_IHPSG13_",
    help="Master-name prefix identifying the SRAM macros",
)
@click_odb
def power_columns(reader, layer_name, rail_layer_name, macro_prefix):
    block = reader.block
    tech = reader.tech
    layer = tech.findLayer(layer_name)
    if layer is None:
        raise click.ClickException(f"Layer {layer_name} not found")

    srams = [
        inst
        for inst in block.getInsts()
        if inst.getMaster().isBlock()
        and inst.getMaster().getName().startswith(macro_prefix)
    ]
    if not srams:
        print(f"[INFO] No {macro_prefix}* macros: nothing to do.")
        return

    for inst in srams:
        if inst.getOrient() != "R0":
            raise click.ClickException(
                f"{inst.getName()}: orientation {inst.getOrient()} is not supported, place the SRAM at R0"
            )

    # --- Collect each macro's supply pins, keyed by the net they connect to.
    # columns[net] = list of (x0, x1, y0, y1, macro_bbox), die coordinates
    columns = {}
    for inst in srams:
        bbox = inst.getBBox()
        for iterm in inst.getITerms():
            mterm = iterm.getMTerm()
            if mterm.getSigType() not in ("POWER", "GROUND"):
                continue
            net = iterm.getNet()
            if net is None:
                raise click.ClickException(
                    f"{inst.getName()}/{mterm.getName()} is not connected to a power net; "
                    "check PDN_MACRO_CONNECTIONS"
                )
            for mpin in mterm.getMPins():
                for geo in mpin.getGeometry():
                    if geo.getTechLayer() is None or geo.getTechLayer().getName() != layer_name:
                        continue
                    columns.setdefault(net.getName(), []).append(
                        (
                            bbox.xMin() + geo.xMin(),
                            bbox.xMin() + geo.xMax(),
                            bbox.yMin() + geo.yMin(),
                            bbox.yMin() + geo.yMax(),
                            bbox,
                        )
                    )

    # --- Full stripe height, taken from pdngen's own untrimmed stripes.
    stripes = {}
    for net_name in columns:
        net = block.findNet(net_name)
        stripes[net_name] = [
            box
            for swire in net.getSWires()
            for box in swire.getWires()
            if not box.isVia()
            and box.getTechLayer().getName() == layer_name
            and is_vertical(box)
        ]
    all_stripes = [b for boxes in stripes.values() for b in boxes]
    if not all_stripes:
        raise click.ClickException(f"No {layer_name} stripes found: did GeneratePDN run?")
    y_lo = min(b.yMin() for b in all_stripes)
    y_hi = max(b.yMax() for b in all_stripes)

    def is_full_height(box):
        return box.yMin() <= y_lo and box.yMax() >= y_hi

    def crosses_a_macro(box):
        return any(x_overlaps(box, s.getBBox().xMin(), s.getBBox().xMax()) for s in srams)

    for net_name, pins in columns.items():
        net = block.findNet(net_name)
        swire = net.getSWires()[0]
        wires = [b for sw in net.getSWires() for b in sw.getWires()]
        bpins = [bpin for bterm in net.getBTerms() for bpin in bterm.getBPins()]
        rails = [
            b
            for b in wires
            if not b.isVia()
            and b.getTechLayer().getName() == rail_layer_name
            and not is_vertical(b)
        ]

        # The via stack pdngen puts where a full stripe crosses a rail:
        # every via sitting at one such crossing point.
        via_stack = []
        for stripe in stripes[net_name]:
            if not is_full_height(stripe) or crosses_a_macro(stripe):
                continue
            cx = centre(stripe.xMin(), stripe.xMax())
            by_y = {}
            for b in wires:
                if b.isVia():
                    x, y = b.getViaXY()
                    if x == cx:
                        by_y.setdefault(y, []).append(b)
            if by_y:
                via_stack = max(by_y.values(), key=len)
                break
        if not via_stack:
            raise click.ClickException(f"{net_name}: no rail via stack found to copy")
        via_masters = [b.getBlockVia() or b.getTechVia() for b in via_stack]

        # 1. Remove trimmed stripes and stripes crossing a macro.
        doomed = [
            s for s in stripes[net_name] if not is_full_height(s) or crosses_a_macro(s)
        ]
        doomed_x = sorted({(s.xMin(), s.xMax()) for s in doomed})

        def via_on_doomed_stripe(via):
            vx = via.getViaXY()[0]
            return any(x0 <= vx <= x1 for (x0, x1) in doomed_x)

        removed_vias = 0
        for b in wires:
            if b.isVia() and via_on_doomed_stripe(b):
                odb.dbSBox_destroy(b)
                removed_vias += 1
        for s in doomed:
            odb.dbSBox_destroy(s)
        removed_pins = 0
        for bpin in bpins:
            for box in list(bpin.getBoxes()):
                if box.getTechLayer().getName() == layer_name and any(
                    x_overlaps(box, x0, x1) for (x0, x1) in doomed_x
                ):
                    odb.dbBox_destroy(box)
                    removed_pins += 1
        print(
            f"[INFO] {net_name}: removed {len(doomed)} trimmed/crossing stripe segments "
            f"at {len(doomed_x)} x positions, {removed_vias} vias, {removed_pins} pin shapes"
        )

        # 2. + 3. Draw a stripe on every supply pin, with rail vias outside the macro.
        full = partial = vias = 0
        for x0, x1, p_lo, p_hi, bbox in pins:
            touches_bottom = p_lo <= bbox.yMin()
            touches_top = p_hi >= bbox.yMax()
            if touches_bottom and touches_top:
                s_lo, s_hi = y_lo, y_hi
            elif touches_bottom:
                s_lo, s_hi = y_lo, p_hi
            elif touches_top:
                s_lo, s_hi = p_lo, y_hi
            else:
                print(
                    f"[WARNING] {net_name}: pin at x={x0 / 1000:.3f} touches neither macro edge, skipped"
                )
                continue

            odb.dbSBox_create(swire, layer, x0, s_lo, x1, s_hi, "STRIPE")
            if s_lo == y_lo and s_hi == y_hi:
                if bpins:
                    odb.dbBox_create(bpins[0], layer, x0, s_lo, x1, s_hi)
                full += 1
            else:
                partial += 1

            cx = centre(x0, x1)
            for rail in rails:
                ry = centre(rail.yMin(), rail.yMax())
                inside_macro = bbox.yMin() <= ry <= bbox.yMax()
                if inside_macro or not (s_lo <= ry <= s_hi):
                    continue
                if not (rail.xMin() <= x0 and x1 <= rail.xMax()):
                    continue
                for via in via_masters:
                    odb.dbSBox_create(swire, via, cx, ry, "STRIPE")
                vias += 1

        print(
            f"[INFO] {net_name}: drew {full} full-height pin stripes and {partial} "
            f"one-sided stripes on SRAM supply pins, with {vias} rail via stacks"
        )


if __name__ == "__main__":
    power_columns()
