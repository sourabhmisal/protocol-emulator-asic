/*
 * Copyright (c) 2024 Sourabh Misal
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_sourabhmisal_protocol_emulator (
    input  wire [7:0] ui_in,    // Dedicated inputs: half-period load value / SRAM address or data byte
    output wire [7:0] uo_out,   // Dedicated outputs: uo_out[0] = square wave, or SRAM read data
    input  wire [7:0] uio_in,   // IOs: Input path (uio_in[0] = load, [3:1] = SRAM command, [4] = output select)
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

  // SRAM plumbing test: the IHP 1024x8 SRAM macro, reached through a
  // one-byte command port so it fits the spare pins.
  //
  //   uio_in[3:1] : command, acted on in the cycle it is held
  //     1 ADDR_LO  sram_addr[7:0] <= ui_in
  //     2 ADDR_HI  sram_addr[9:8] <= ui_in[1:0]
  //     3 WRITE    SRAM[sram_addr] <= ui_in
  //     4 READ     SRAM read data <= SRAM[sram_addr]
  //     0, 5-7     no operation
  //   uio_in[4]   : 0 = uo_out shows the square wave, 1 = the SRAM read data
  //
  // Every macro input comes straight from a flop, so the macro never sees
  // the pad-to-core delay of an input pin.  A command is registered on the
  // edge that samples it and the macro acts on the next edge, where A_DOUT
  // updates for a READ and holds until the next READ.

  localparam CMD_ADDR_LO = 3'd1;
  localparam CMD_ADDR_HI = 3'd2;
  localparam CMD_WRITE   = 3'd3;
  localparam CMD_READ    = 3'd4;

  wire [2:0] cmd        = uio_in[3:1];
  wire       show_sram  = uio_in[4];

  reg  [9:0] sram_addr;
  reg  [7:0] sram_din;
  reg        sram_wen;
  reg        sram_ren;
  wire [7:0] sram_dout;

  always @(posedge clk) begin
    if (!rst_n) begin
      sram_addr <= 10'd0;
      sram_din  <= 8'd0;
      sram_wen  <= 1'b0;
      sram_ren  <= 1'b0;
    end else begin
      sram_wen <= (cmd == CMD_WRITE);
      sram_ren <= (cmd == CMD_READ);
      if (cmd == CMD_ADDR_LO) sram_addr[7:0] <= ui_in;
      if (cmd == CMD_ADDR_HI) sram_addr[9:8] <= ui_in[1:0];
      if (cmd == CMD_WRITE)   sram_din       <= ui_in;
    end
  end

  RM_IHPSG13_1P_1024x8_c2_bm_bist sram (
      .A_CLK      (clk),
      .A_MEN      (sram_wen | sram_ren),  // memory enable: only during an access
      .A_WEN      (sram_wen),
      .A_REN      (sram_ren),
      .A_ADDR     (sram_addr),
      .A_DIN      (sram_din),
      .A_DLY      (1'b1),                 // datasheet: tie high
      .A_DOUT     (sram_dout),
      .A_BM       (8'hFF),                // write all eight bits

      // Built-in self-test port, unused: A_BIST_EN low leaves the
      // functional port in control, and the rest are tied off.
      .A_BIST_CLK (1'b0),
      .A_BIST_EN  (1'b0),
      .A_BIST_MEN (1'b0),
      .A_BIST_WEN (1'b0),
      .A_BIST_REN (1'b0),
      .A_BIST_ADDR(10'd0),
      .A_BIST_DIN (8'd0),
      .A_BIST_BM  (8'd0)
  );

  assign uo_out  = show_sram ? sram_dout : {7'b0, wave_out};
  assign uio_out = 8'b0;
  assign uio_oe  = 8'b0;

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in[7:5], 1'b0};

endmodule
