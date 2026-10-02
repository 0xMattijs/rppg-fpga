// Testbench for skin_mask and grid_accumulator: three frames of pseudo-random
// pixels through both, each cell's sums checked against a model.
// Run with:
//   iverilog -o tb hdl/sim/tb_grid_accumulator.v hdl/src/skin_mask.v \
//     hdl/src/grid_accumulator.v && vvp tb
//
// Frame 0 has the mask on, frame 1 off, and frame 2 on with an ROI whose
// size isn't a multiple of 4, so the last column and row take the
// remainder; it also leaves the bottom row of cells empty by keeping the
// skin pixels out of it. Pixels come every 8 cycles, as from the camera.
`timescale 1ns/1ps
module tb_grid_accumulator;
    localparam W = 40, H = 24;

    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg        frame_tick = 0, pix_valid = 0, mask_en = 1;
    reg [10:0] x = 0, x0, x1;
    reg [9:0]  y = 0, y0, y1;
    reg [7:0]  r = 0, g = 0, b = 0;
    reg [3:0]  rd_cell = 0;

    wire        sk_valid, sk_skin;
    wire [10:0] sk_x;
    wire [9:0]  sk_y;
    wire [7:0]  sk_r, sk_g, sk_b;
    wire [23:0] rd_r, rd_g, rd_b;
    wire [15:0] rd_n;

    skin_mask u_skin (
        .clk(clk), .rst_n(rst_n),
        .pix_valid(pix_valid), .pix_x(x), .pix_y(y),
        .pix_r(r), .pix_g(g), .pix_b(b),
        .y_min(8'd40), .y_max(8'd235), .cb_min(8'd77), .cb_max(8'd127),
        .cr_min(8'd133), .cr_max(8'd173),
        .out_valid(sk_valid), .out_x(sk_x), .out_y(sk_y),
        .out_r(sk_r), .out_g(sk_g), .out_b(sk_b), .skin(sk_skin)
    );

    grid_accumulator dut (
        .clk(clk), .rst_n(rst_n),
        .frame_tick(frame_tick), .pix_valid(sk_valid), .pix_x(sk_x), .pix_y(sk_y),
        .pix_r(sk_r), .pix_g(sk_g), .pix_b(sk_b), .skin(sk_skin), .mask_en(mask_en),
        .roi_x0(x0), .roi_x1(x1), .roi_y0(y0), .roi_y1(y1),
        .rd_cell(rd_cell), .rd_r(rd_r), .rd_g(rd_g), .rd_b(rd_b), .rd_n(rd_n)
    );

    // Model
    integer exp_r [0:15], exp_g [0:15], exp_b [0:15], exp_n [0:15];
    integer i, j, c, frame, errors = 0, skin_px = 0, other_px = 0;
    integer luma, cb, cr, col, row, seed = 1;
    reg     is_skin;

    task model_pixel;
        begin
            luma = (77 * r + 150 * g + 29 * b) >> 8;
            cb = (32768 - 43 * r - 85 * g + 128 * b) >> 8;
            cr = (32768 + 128 * r - 107 * g - 21 * b) >> 8;
            is_skin = luma >= 40 && luma <= 235 && cb >= 77 && cb <= 127 &&
                      cr >= 133 && cr <= 173;
            if (is_skin) skin_px = skin_px + 1; else other_px = other_px + 1;
            if ((is_skin || !mask_en) && x >= x0 && x < x1 && y >= y0 && y < y1) begin
                // The fabric places the third edge at w/2 + w/4, which can
                // be one short of 3w/4.
                col = x >= x0 + (x1 - x0) / 2 + (x1 - x0) / 4 ? 3 :
                      x >= x0 + (x1 - x0) / 2 ? 2 : x >= x0 + (x1 - x0) / 4 ? 1 : 0;
                row = y >= y0 + (y1 - y0) / 2 + (y1 - y0) / 4 ? 3 :
                      y >= y0 + (y1 - y0) / 2 ? 2 : y >= y0 + (y1 - y0) / 4 ? 1 : 0;
                c = 4 * row + col;
                exp_r[c] = exp_r[c] + r; exp_g[c] = exp_g[c] + g;
                exp_b[c] = exp_b[c] + b; exp_n[c] = exp_n[c] + 1;
            end
        end
    endtask

    task send_frame;
        input integer skin_rows;   // rows from the top that may hold skin
        begin
            for (c = 0; c < 16; c = c + 1) begin
                exp_r[c] = 0; exp_g[c] = 0; exp_b[c] = 0; exp_n[c] = 0;
            end
            for (j = 0; j < H; j = j + 1)
                for (i = 0; i < W; i = i + 1) begin
                    x = i; y = j;
                    // Half skin tones around (170, 120, 100), half anything; dark
                    // from skin_rows down.
                    if (($random(seed) & 1) && j < skin_rows) begin
                        r = 150 + ($random(seed) & 63);
                        g = 100 + ($random(seed) & 31);
                        b = 80 + ($random(seed) & 31);
                    end else if (j < skin_rows) begin
                        r = $random(seed); g = $random(seed); b = $random(seed);
                    end else begin
                        // Too dark for skin
                        r = $random(seed) & 31; g = $random(seed) & 31;
                        b = $random(seed) & 31;
                    end
                    model_pixel;
                    pix_valid = 1;
                    @(posedge clk) #1 pix_valid = 0;
                    repeat (7) @(posedge clk);
                    #1;
                end
            repeat (20) @(posedge clk);
            #1 frame_tick = 1;
            @(posedge clk) #1 frame_tick = 0;
        end
    endtask

    task check_frame;
        begin
            for (c = 0; c < 16; c = c + 1) begin
                rd_cell = c;
                @(posedge clk) #1;
                if (rd_r != exp_r[c] || rd_g != exp_g[c] || rd_b != exp_b[c] ||
                    rd_n != exp_n[c]) begin
                    errors = errors + 1;
                    $display("frame %0d cell %0d: got n=%0d r=%0d g=%0d b=%0d, want n=%0d r=%0d g=%0d b=%0d",
                             frame, c, rd_n, rd_r, rd_g, rd_b,
                             exp_n[c], exp_r[c], exp_g[c], exp_b[c]);
                end
            end
        end
    endtask

    initial begin
        x0 = 4; x1 = 36; y0 = 2; y1 = 18;
        #20 rst_n = 1;
        @(posedge clk) #1 frame_tick = 1;
        @(posedge clk) #1 frame_tick = 0;

        frame = 0; mask_en = 1;
        send_frame(H);
        check_frame;

        frame = 1; mask_en = 0;
        send_frame(H);
        // Reading the last frame while the next one fills must still work:
        // check it during frame 2's first pixels.
        check_frame;

        frame = 2; mask_en = 1;
        x0 = 3; x1 = 37; y0 = 1; y1 = 23;      // 34 x 22: remainders of 2
        // Bottom cell row: y >= 1 + 11 + 5 = 17.
        send_frame(17);
        check_frame;
        // The bottom row of cells must be empty.
        for (c = 12; c < 16; c = c + 1)
            if (exp_n[c] != 0) begin
                errors = errors + 1;
                $display("test setup: cell %0d should be empty", c);
            end

        if (errors == 0 && skin_px > 100 && other_px > 100)
            $display("PASS (%0d skin and %0d other pixels)", skin_px, other_px);
        else
            $display("FAIL: %0d errors, %0d skin and %0d other pixels",
                     errors, skin_px, other_px);
        $finish;
    end
endmodule
