/*
 * Copyright (c) 2024 Sourabh Misal
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_sourabhmisal_protocol_emulator (
    input  wire [7:0] ui_in,    // Dedicated inputs: half-period load value
    output wire [7:0] uo_out,   // Dedicated outputs: uo_out[0] = square wave
    input  wire [7:0] uio_in,   // IOs: Input path (uio_in[0] = load strobe)
    output wire [7:0] uio_out,  // IOs: Output path (unused here)
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // Programmable square-wave generator.
  //
  //   half_period : loadable reload value for the down-counter
  //   count       : down-counter; reloads from half_period and toggles
  //                 wave_out whenever it reaches its terminal count (0)
  //   wave_out    : toggles every (half_period + 1) clock cycles, so the
  //                 output period is 2 * (half_period + 1) clock cycles
  //
  // Pulsing uio_in[0] (load) for one clock cycle latches ui_in into
  // half_period AND reloads count immediately, so a newly written period
  // takes effect on the very next edge instead of waiting for the counter
  // that was already in flight to expire.

  wire load = uio_in[0];

  reg [7:0] half_period;
  reg [7:0] count;
  reg       wave_out;

  always @(posedge clk) begin
    if (!rst_n) begin
      half_period <= 8'd0;
      count       <= 8'd0;
      wave_out    <= 1'b0;
    end else if (load) begin
      half_period <= ui_in;
      count       <= ui_in;
    end else if (count == 8'd0) begin
      count    <= half_period;
      wave_out <= ~wave_out;
    end else begin
      count <= count - 8'd1;
    end
  end

  assign uo_out  = {7'b0, wave_out};
  assign uio_out = 8'b0;
  assign uio_oe  = 8'b0;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in[7:1], 1'b0};

endmodule
