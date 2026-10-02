// ROI accumulator (Phase 2).
// Sums R, G and B for pixels inside a rectangle and latches the totals at
// frame end. cam_bus.v feeds it; rppg_top.v puts the results on APB.
module roi_accumulator #(
    parameter CW = 8,   // bits per color channel, after expansion from RGB565
    parameter XW = 11,
    parameter YW = 10,
    parameter SW = 32   // sum width: 640*480*255 < 2^27
) (
    input  wire          clk,
    input  wire          rst_n,

    // Pixel stream
    input  wire          frame_start,
    input  wire          frame_end,
    input  wire          pix_valid,
    input  wire [XW-1:0] pix_x,
    input  wire [YW-1:0] pix_y,
    input  wire [CW-1:0] pix_r,
    input  wire [CW-1:0] pix_g,
    input  wire [CW-1:0] pix_b,

    // ROI, set by the Cortex-M3
    input  wire [XW-1:0] roi_x0,
    input  wire [XW-1:0] roi_x1,
    input  wire [YW-1:0] roi_y0,
    input  wire [YW-1:0] roi_y1,

    // Latched results
    output reg  [SW-1:0] sum_r,
    output reg  [SW-1:0] sum_g,
    output reg  [SW-1:0] sum_b,
    output reg  [SW-1:0] pix_count,
    output reg  [31:0]   frame_count,
    output reg           frame_irq     // one-cycle pulse when results update
);

    reg [SW-1:0] acc_r, acc_g, acc_b, acc_n;

    wire in_roi = pix_valid &&
                  pix_x >= roi_x0 && pix_x < roi_x1 &&
                  pix_y >= roi_y0 && pix_y < roi_y1;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc_r <= 0; acc_g <= 0; acc_b <= 0; acc_n <= 0;
            sum_r <= 0; sum_g <= 0; sum_b <= 0; pix_count <= 0;
            frame_count <= 0;
            frame_irq   <= 1'b0;
        end else begin
            frame_irq <= 1'b0;

            if (frame_start) begin
                acc_r <= 0; acc_g <= 0; acc_b <= 0; acc_n <= 0;
            end else if (in_roi) begin
                acc_r <= acc_r + pix_r;
                acc_g <= acc_g + pix_g;
                acc_b <= acc_b + pix_b;
                acc_n <= acc_n + 1'b1;
            end

            if (frame_end) begin
                sum_r       <= acc_r;
                sum_g       <= acc_g;
                sum_b       <= acc_b;
                pix_count   <= acc_n;
                frame_count <= frame_count + 1'b1;
                frame_irq   <= 1'b1;
            end
        end
    end

endmodule
