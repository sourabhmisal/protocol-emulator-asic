## How it works

This is the unmodified Tiny Tapeout example design, used to verify that the build flow and submission pipeline work end to end. It is a purely combinational 8-bit adder: the eight dedicated input pins are operand A, the eight bidirectional pins (configured as inputs) are operand B, and their sum is driven onto the eight dedicated output pins. There is no internal state, so the clock and reset inputs are unused.

## How to test

Set the DIP switches on the demo board to a value for operand A. Drive operand B on the bidirectional pins, or leave them at zero. The sum appears on the output pins and can be read on the demo board LEDs or via the Tiny Tapeout Commander.

To run the testbench locally:

    cd test
    make

## External hardware

None. The design runs standalone on the demo board.
