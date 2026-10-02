// Testbench for roi_accumulator: a 16x8 frame of constant color with a 4x4 ROI.
// Run with: iverilog -o tb hdl/sim/tb_roi_accumulator.v hdl/src/roi_accumulator.v && vvp tb
`timescale 1ns/1ps
module tb_roi_accumulator;
    reg clk = 0, rst_n = 0;
    reg frame_start = 0, frame_end = 0, pix_valid = 0;
    reg [10:0] x; reg [9:0] y;
    wire [31:0] sr, sg, sb, n, fc;
    wire irq;

    always #5 clk = ~clk;

    roi_accumulator dut (
        .clk(clk), .rst_n(rst_n),
        .frame_start(frame_start), .frame_end(frame_end), .pix_valid(pix_valid),
        .pix_x(x), .pix_y(y), .pix_r(8'd10), .pix_g(8'd20), .pix_b(8'd30),
        .roi_x0(11'd4), .roi_x1(11'd8), .roi_y0(10'd2), .roi_y1(10'd6),
        .sum_r(sr), .sum_g(sg), .sum_b(sb), .pix_count(n),
        .frame_count(fc), .frame_irq(irq)
    );

    integer i, j;
    initial begin
        #20 rst_n = 1;
        @(posedge clk) frame_start = 1;
        @(posedge clk) frame_start = 0;
        for (j = 0; j < 8; j = j + 1)
            for (i = 0; i < 16; i = i + 1) begin
                x = i; y = j; pix_valid = 1;
                @(posedge clk);
            end
        pix_valid = 0;
        frame_end = 1; @(posedge clk); frame_end = 0;
        @(posedge clk);
        if (n == 16 && sr == 160 && sg == 320 && sb == 480 && fc == 1)
            $display("PASS");
        else
            $display("FAIL: n=%0d r=%0d g=%0d b=%0d fc=%0d", n, sr, sg, sb, fc);
        $finish;
    end
endmodule
