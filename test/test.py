# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# uio_in[0] is the load strobe: holding it high for one clock cycle latches
# ui_in into the half-period register and reloads the down-counter.
LOAD_BIT = 1 << 0


async def start_clock_and_reset(dut):
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def load_half_period(dut, value):
    """Pulse the load strobe for one clock cycle to program a new half-period.

    A value driven onto a DUT input from a cocotb coroutine is not sampled by
    the design until the clock edge *after* the next one (cocotb/Icarus only
    guarantee the write is visible from the following ReadWrite phase
    onward), so an extra settle cycle after de-asserting the strobe is needed
    before the load is guaranteed to have been latched.
    """
    dut.ui_in.value = value
    dut.uio_in.value = LOAD_BIT
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 1)


async def measure_half_period_cycles(dut, timeout_cycles=1000):
    """Count clock cycles from now until the wave output (uo_out[0]) next toggles."""
    prev = int(dut.uo_out.value) & 1
    for cycles in range(1, timeout_cycles + 1):
        await ClockCycles(dut.clk, 1)
        cur = int(dut.uo_out.value) & 1
        if cur != prev:
            return cycles
    raise TimeoutError("wave output never toggled")


@cocotb.test()
async def test_reset(dut):
    """After reset, the wave output and all uio pins must be held low."""
    dut._log.info("Start")

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)

    assert dut.uo_out.value == 0
    assert dut.uio_out.value == 0
    assert dut.uio_oe.value == 0

    dut.rst_n.value = 1


@cocotb.test()
async def test_period_matches_loaded_value(dut):
    """Measure the toggle interval in clock cycles and check it against the
    loaded half-period, for several different loaded values."""
    dut._log.info("Start")
    await start_clock_and_reset(dut)

    for half_period in (0, 1, 5, 20, 100, 255):
        await load_half_period(dut, half_period)

        expected_cycles = half_period + 1

        # Measure two consecutive half-periods to make sure the counter
        # free-runs correctly after the first reload, not just once.
        first = await measure_half_period_cycles(dut)
        second = await measure_half_period_cycles(dut)

        assert first == expected_cycles, (
            f"half_period={half_period}: expected {expected_cycles} clk cycles "
            f"between toggles, measured {first}"
        )
        assert second == expected_cycles, (
            f"half_period={half_period}: expected {expected_cycles} clk cycles "
            f"between toggles, measured {second}"
        )


@cocotb.test()
async def test_reload_takes_effect_immediately(dut):
    """Loading a new half-period mid-count should restart the counter right
    away, rather than waiting for the in-flight count to finish."""
    dut._log.info("Start")
    await start_clock_and_reset(dut)

    await load_half_period(dut, 50)

    # Let the counter run partway, then reprogram to a much shorter period
    # long before the original one would have expired.
    await ClockCycles(dut.clk, 5)
    await load_half_period(dut, 3)

    cycles = await measure_half_period_cycles(dut)
    assert cycles == 4, (
        f"expected the reload to take effect immediately (4 clk cycles), "
        f"measured {cycles}"
    )
