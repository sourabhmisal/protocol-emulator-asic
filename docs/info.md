## How it works

This is an early milestone of a programmable protocol emulator. It has two independent blocks.

**Square-wave generator.** An 8-bit down-counter reloads from a programmable half-period and toggles the output each time it reaches zero, so the output period is 2 × (half_period + 1) clock cycles. Pulsing `load` (uio[0]) for one clock cycle latches `ui[7:0]` as the new half-period and restarts the counter immediately.

**SRAM plumbing test.** An IHP 1024 × 8 SRAM macro (`RM_IHPSG13_1P_1024x8_c2_bm_bist`), which will become the emulator's program memory, is reached through a one-byte command port. Each command is held on `sram_cmd` (uio[3:1]) for one clock cycle, with its operand on `ui[7:0]`:

| sram_cmd | Command | Effect |
|---|---|---|
| 1 | ADDR_LO | address[7:0] ← ui[7:0] |
| 2 | ADDR_HI | address[9:8] ← ui[1:0] |
| 3 | WRITE | SRAM[address] ← ui[7:0] |
| 4 | READ | read data ← SRAM[address] |
| 0, 5–7 | — | no operation |

`show_sram` (uio[4]) selects what drives the outputs: low for the square wave on uo[0] (uo[7:1] low), high for the last SRAM read data on uo[7:0]. Read data appears two clock cycles after the READ command and holds until the next READ.

## How to test

Square wave: set the half-period on the input DIP switches, pulse uio[0] for one clock, and observe uo[0] with a logic analyser or scope.

SRAM: with uio[4] high, issue ADDR_LO and ADDR_HI to select an address, then WRITE a byte or READ one back and check uo[7:0].

To run the testbench locally, which covers both blocks and writes and reads back every SRAM address:

    cd test
    make

## External hardware

None. The design runs standalone on the demo board.
