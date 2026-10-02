// Testbench for overlay: checks every pixel of a 640 x 480 frame against a
// model of the layout, without and with mirroring. Run with:
//   iverilog -o tb hdl/sim/tb_overlay.v hdl/src/overlay.v && vvp tb
`timescale 1ns/1ps
module tb_overlay;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg  [10:0] x = 0;
    reg  [9:0]  y = 0;
    reg         enable = 0, mirror = 0, test = 0;
    reg  [20:0] digits;
    reg  [7:0]  bar_len;
    reg  [15:0] bar_color;
    reg         we = 0;
    reg  [7:0]  waddr = 0;
    reg  [13:0] wdata = 0;
    wire [1:0]  mode;
    wire [15:0] color;

    overlay dut (
        .clk(clk), .rst_n(rst_n), .x(x), .y(y),
        .enable(enable), .mirror(mirror), .test(test), .digit_segs(digits),
        .bar_len(bar_len), .bar_color(bar_color),
        .digit_color(16'hFE9C), .wave_color(16'hFE00),
        .wave_we(we), .wave_waddr(waddr), .wave_wdata(wdata),
        .mode(mode), .color(color)
    );

    // Waveform column c covers rows lo(c)..hi(c); column 7 is empty.
    function [6:0] lo(input integer c); lo = c % 70; endfunction
    function [6:0] hi(input integer c); hi = c == 7 ? 0 : c % 70 + c % 5 + 2; endfunction

    // Seven segments, gfedcba, for a pixel at (dx, dy) in a 56 x 104 cell.
    function [6:0] segs_at(input integer dx, input integer dy);
        begin
            segs_at = 0;
            if (dy < 12)              segs_at = segs_at | 7'b0000001;  // a
            if (dx >= 44 && dy < 58)  segs_at = segs_at | 7'b0000010;  // b
            if (dx >= 44 && dy >= 46) segs_at = segs_at | 7'b0000100;  // c
            if (dy >= 92)             segs_at = segs_at | 7'b0001000;  // d
            if (dx < 12 && dy >= 46)  segs_at = segs_at | 7'b0010000;  // e
            if (dx < 12 && dy < 58)   segs_at = segs_at | 7'b0100000;  // f
            if (dy >= 46 && dy < 58)  segs_at = segs_at | 7'b1000000;  // g
        end
    endfunction

    // Expected {mode, color} for pixel (px, py).
    reg [1:0]  e_mode;
    reg [15:0] e_color;
    task expect_at(input integer px, input integer py);
        integer ox, d, dx, c;
        reg [6:0] lit;
        begin
            ox = mirror ? 639 - px : px;
            e_mode = 0; e_color = 0;
            lit = 0;
            for (d = 0; d < 3; d = d + 1) begin
                dx = ox - (16 + 72 * d);
                if (dx >= 0 && dx < 56 && py >= 16 && py < 120)
                    lit = segs_at(dx, py - 16) & digits[7 * d +: 7];
            end
            c = ox / 4;
            if (lit != 0) begin
                e_mode = 1; e_color = 16'hFE9C;
            end else if (ox >= 16 && ox < 216 && py >= 128 && py < 148) begin
                e_mode = 1; e_color = ox < 16 + bar_len ? bar_color : 16'h2104;
            end else if (py >= 384 && py < 464 && py - 384 >= lo(c) && py - 384 <= hi(c)) begin
                e_mode = 1; e_color = 16'hFE00;
            end else if ((ox >= 8 && ox < 232 && py >= 8 && py < 160) ||
                         (py >= 376 && py < 472)) begin
                e_mode = 2;
            end
        end
    endtask

    integer errors = 0, px, py, c, pass;

    initial begin
        #100 rst_n = 1;
        for (c = 0; c < 160; c = c + 1) begin
            @(posedge clk) begin we <= 1; waddr <= c; wdata <= {hi(c), lo(c)}; end
        end
        // Past the end: must not wrap onto column 0.
        @(posedge clk) begin waddr <= 200; wdata <= 14'h3FFF; end
        @(posedge clk) we <= 0;

        digits = {7'b1111111, 7'b0000110, 7'b1001111};   // "318", leftmost last
        bar_len = 77;
        bar_color = 16'h07E0;
        enable = 1;

        for (pass = 0; pass < 2; pass = pass + 1) begin
            mirror = pass;
            for (py = 0; py < 480; py = py + 1)
                for (px = 0; px < 640; px = px + 1) begin
                    @(posedge clk) begin x <= px; y <= py; end
                    repeat (3) @(posedge clk);
                    expect_at(px, py);
                    if (mode !== e_mode || (e_mode == 1 && color !== e_color)) begin
                        if (errors < 10)
                            $display("FAIL: mirror %0d (%0d,%0d) mode %0d color %h, expected %0d %h",
                                     mirror, px, py, mode, color, e_mode, e_color);
                        errors = errors + 1;
                    end
                end
        end

        // Test pattern, mirrored: bars, then one patch per bit.
        test = 1;
        mirror = 1;
        for (py = 0; py < 480; py = py + 7)
            for (px = 0; px < 640; px = px + 1) begin
                @(posedge clk) begin x <= px; y <= py; end
                repeat (3) @(posedge clk);
                c = 639 - px;
                if (py < 320)
                    e_color = c < 80 ? 16'hFFFF : c < 160 ? 16'hFFE0 : c < 240 ? 16'h07FF :
                              c < 320 ? 16'h07E0 : c < 400 ? 16'hF81F : c < 480 ? 16'hF800 :
                              c < 560 ? 16'h001F : 16'h0000;
                else
                    e_color = c / 32 < 16 ? 16'h8000 >> (c / 32) : 16'h0000;
                if (mode !== 1 || color !== e_color) begin
                    if (errors < 10)
                        $display("FAIL: test pattern (%0d,%0d) mode %0d color %h, expected %h",
                                 px, py, mode, color, e_color);
                    errors = errors + 1;
                end
            end
        test = 0;

        enable = 0;
        @(posedge clk) begin x <= 20; y <= 20; end
        repeat (3) @(posedge clk);
        if (mode !== 0) begin
            $display("FAIL: overlay off but mode %0d", mode);
            errors = errors + 1;
        end

        if (errors == 0) $display("PASS");
        else $display("%0d errors", errors);
        $finish;
    end
endmodule
