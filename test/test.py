# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# uio_in[0] is the load strobe: holding it high for one clock cycle latches
# ui_in into the half-period register and reloads the down-counter.
LOAD_BIT = 1 << 0

# uio_in[3:1] is the SRAM command; uio_in[4] switches uo_out to SRAM data.
CMD_SHIFT = 1
CMD_ADDR_LO = 1
CMD_ADDR_HI = 2
CMD_WRITE = 3
CMD_READ = 4
SHOW_SRAM_BIT = 1 << 4
SRAM_WORDS = 1024


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


async def sram_command(dut, cmd, value=0, show_sram=True):
    """Hold an SRAM command on uio_in[3:1] for one clock cycle.

    Like load_half_period(), this waits one extra settle cycle so the DUT is
    guaranteed to have sampled the command before the next one is driven.
    """
    show = SHOW_SRAM_BIT if show_sram else 0
    dut.ui_in.value = value
    dut.uio_in.value = show | (cmd << CMD_SHIFT)
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = show
    await ClockCycles(dut.clk, 1)


async def sram_write(dut, addr, value, show_sram=True):
    await sram_command(dut, CMD_ADDR_LO, addr & 0xFF, show_sram)
    await sram_command(dut, CMD_ADDR_HI, addr >> 8, show_sram)
    await sram_command(dut, CMD_WRITE, value, show_sram)


async def sram_read(dut, addr):
    await sram_command(dut, CMD_ADDR_LO, addr & 0xFF)
    await sram_command(dut, CMD_ADDR_HI, addr >> 8)
    await sram_command(dut, CMD_READ)
    # The command is registered on one edge and the macro reads on the next.
    await ClockCycles(dut.clk, 2)
    return int(dut.uo_out.value)


def pattern(addr):
    """A value that differs between neighbouring addresses and between the
    two halves of the address space, so address aliasing shows up."""
    return ((addr * 37) ^ (addr >> 8) ^ 0x5A) & 0xFF


@cocotb.test()
async def test_sram_write_read_patterns(dut):
    """Write edge-case values to edge-case addresses, then read them all back.

    Everything is written before anything is read, so a write landing on the
    wrong address overwrites a neighbour and is caught.
    """
    dut._log.info("Start")
    await start_clock_and_reset(dut)

    cases = {
        0: 0x00,
        1: 0xFF,
        2: 0xAA,
        3: 0x55,
        255: 0x01,
        256: 0x80,
        511: 0x7E,
        512: 0x81,
        1022: 0xC3,
        1023: 0x3C,
    }
    for addr, value in cases.items():
        await sram_write(dut, addr, value)

    for addr, value in cases.items():
        got = await sram_read(dut, addr)
        assert got == value, f"SRAM[{addr}]: wrote 0x{value:02X}, read 0x{got:02X}"


@cocotb.test()
async def test_sram_every_address(dut):
    """Fill all 1024 bytes with an address-dependent pattern and read it back."""
    dut._log.info("Start")
    await start_clock_and_reset(dut)

    for addr in range(SRAM_WORDS):
        await sram_write(dut, addr, pattern(addr))

    for addr in range(SRAM_WORDS):
        got = await sram_read(dut, addr)
        assert got == pattern(addr), (
            f"SRAM[{addr}]: wrote 0x{pattern(addr):02X}, read 0x{got:02X}"
        )


@cocotb.test()
async def test_sram_does_not_disturb_wave(dut):
    """SRAM traffic must not affect the square-wave generator, and the wave
    stays on uo_out[0] while the output select is low."""
    dut._log.info("Start")
    await start_clock_and_reset(dut)

    await load_half_period(dut, 30)
    for addr in range(4):
        await sram_write(dut, addr, 0xFF, show_sram=False)

    first = await measure_half_period_cycles(dut)
    second = await measure_half_period_cycles(dut)
    # The SRAM writes above take far longer than one half-period, so `first`
    # may start mid-count; `second` is a full, undisturbed half-period.
    assert first <= 31
    assert second == 31, f"expected 31 clk cycles between toggles, measured {second}"
