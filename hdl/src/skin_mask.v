// Skin mask (Phase 6): flags pixels whose YCbCr color falls inside a box.
//
// Passes the pixel stream from cam_bus through two pipeline stages and adds
// skin, which grid_accumulator.v and thumb.v use. frame_tick is not
// delayed: VSYNC rises during the vertical blank, lines after the last
// pixel, so no pixel is in flight.
//
// YCbCr is full-range BT.601 (JPEG), the space of the usual skin boxes
// such as Chai and Ngan's 77 <= Cb <= 127, 133 <= Cr <= 173:
//   Y  =       ( 77 R + 150 G +  29 B) / 256
//   Cb = 128 + (-43 R -  85 G + 128 B) / 256
//   Cr = 128 + (128 R - 107 G -  21 B) / 256
// The limits are inclusive. The Y limits leave out shadows, hair, and
// clipped highlights, which carry no pulse.
module skin_mask #(
    parameter XW = 11,
    parameter YW = 10
) (
    input  wire          clk,
    input  wire          rst_n,

    input  wire          pix_valid,
    input  wire [XW-1:0] pix_x,
    input  wire [YW-1:0] pix_y,
    input  wire [7:0]    pix_r,
    input  wire [7:0]    pix_g,
    input  wire [7:0]    pix_b,

    input  wire [7:0]    y_min,
    input  wire [7:0]    y_max,
    input  wire [7:0]    cb_min,
    input  wire [7:0]    cb_max,
    input  wire [7:0]    cr_min,
    input  wire [7:0]    cr_max,

    // The same pixel, two cycles later
    output reg           out_valid,
    output reg  [XW-1:0] out_x,
    output reg  [YW-1:0] out_y,
    output reg  [7:0]    out_r,
    output reg  [7:0]    out_g,
    output reg  [7:0]    out_b,
    output reg           skin
);

    // Each sum is offset so it can't go negative: 0 .. 65535.
    wire [17:0] r = pix_r, g = pix_g, b = pix_b;
    wire [17:0] y_sum  =          77 * r + 150 * g +  29 * b;
    wire [17:0] cb_sum = 32768 -  43 * r -  85 * g + 128 * b;
    wire [17:0] cr_sum = 32768 + 128 * r - 107 * g -  21 * b;

    reg          s1_valid;
    reg [XW-1:0] s1_x;
    reg [YW-1:0] s1_y;
    reg [7:0]    s1_r, s1_g, s1_b, s1_luma, s1_cb, s1_cr;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s1_valid <= 0; s1_x <= 0; s1_y <= 0;
            s1_r <= 0; s1_g <= 0; s1_b <= 0;
            s1_luma <= 0; s1_cb <= 0; s1_cr <= 0;
            out_valid <= 0; out_x <= 0; out_y <= 0;
            out_r <= 0; out_g <= 0; out_b <= 0; skin <= 0;
        end else begin
            s1_valid <= pix_valid;
            s1_x <= pix_x; s1_y <= pix_y;
            s1_r <= pix_r; s1_g <= pix_g; s1_b <= pix_b;
            s1_luma <= y_sum[15:8];
            s1_cb   <= cb_sum[15:8];
            s1_cr   <= cr_sum[15:8];

            out_valid <= s1_valid;
            out_x <= s1_x; out_y <= s1_y;
            out_r <= s1_r; out_g <= s1_g; out_b <= s1_b;
            skin <= s1_luma >= y_min  && s1_luma <= y_max &&
                    s1_cb   >= cb_min && s1_cb   <= cb_max &&
                    s1_cr   >= cr_min && s1_cr   <= cr_max;
        end
    end

endmodule
