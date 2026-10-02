// ROI grid accumulator (Phase 6): splits the ROI into 4 x 4 cells and sums
// R, G, and B and counts the pixels in each, skin pixels only while
// mask_en is set (skin_mask.v). The cells are numbered row by row from the
// top left of the camera image, 0 to 15. Each is a quarter of the ROI's
// width and height; the right column and bottom row also take the
// remainder.
//
// The sums live in RAM, in two banks: the pixels of one frame go to one
// bank while the Cortex-M3 reads the other, which holds the last complete
// frame. The banks swap at each frame_tick, in the same cycle that
// roi_accumulator latches its sums and counts the frame. Instead of
// clearing a bank, a bit per cell marks whether the cell has been written
// this frame; the first pixel overwrites instead of adding, and a cell with
// no pixels reads as zero.
//
// Each pixel is a read-modify-write over two cycles. cam_bus delivers a
// pixel every two PCLK cycles, eight cycles of clk at 24 MHz, so they
// can't overlap.
module grid_accumulator #(
    parameter XW = 11,
    parameter YW = 10,
    parameter CW = 24,    // R, G, B sums: (640/4 + 3) * (480/4 + 3) * 255 < 2^24
    parameter NW = 16     // pixel count
) (
    input  wire          clk,
    input  wire          rst_n,

    input  wire          frame_tick,  // VSYNC rise: end of one frame, start of the next
    input  wire          pix_valid,
    input  wire [XW-1:0] pix_x,
    input  wire [YW-1:0] pix_y,
    input  wire [7:0]    pix_r,
    input  wire [7:0]    pix_g,
    input  wire [7:0]    pix_b,
    input  wire          skin,
    input  wire          mask_en,

    // ROI for the frame in progress; must hold still between frame_ticks
    input  wire [XW-1:0] roi_x0,
    input  wire [XW-1:0] roi_x1,
    input  wire [YW-1:0] roi_y0,
    input  wire [YW-1:0] roi_y1,

    // Last complete frame: cell rd_cell, valid one cycle after rd_cell
    input  wire [3:0]    rd_cell,
    output wire [CW-1:0] rd_r,
    output wire [CW-1:0] rd_g,
    output wire [CW-1:0] rd_b,
    output wire [NW-1:0] rd_n
);

    // Cell edges for this frame. The ROI changes only at frame_tick, so
    // these settle long before the first pixel.
    wire [XW-1:0] w = roi_x1 - roi_x0;
    wire [YW-1:0] h = roi_y1 - roi_y0;
    reg  [XW-1:0] ex1, ex2, ex3;
    reg  [YW-1:0] ey1, ey2, ey3;
    always @(posedge clk) begin
        ex1 <= roi_x0 + (w >> 2);
        ex2 <= roi_x0 + (w >> 1);
        ex3 <= roi_x0 + (w >> 1) + (w >> 2);
        ey1 <= roi_y0 + (h >> 2);
        ey2 <= roi_y0 + (h >> 1);
        ey3 <= roi_y0 + (h >> 1) + (h >> 2);
    end

    wire [1:0] col = pix_x >= ex3 ? 2'd3 : pix_x >= ex2 ? 2'd2 : pix_x >= ex1 ? 2'd1 : 2'd0;
    wire [1:0] row = pix_y >= ey3 ? 2'd3 : pix_y >= ey2 ? 2'd2 : pix_y >= ey1 ? 2'd1 : 2'd0;
    wire take = pix_valid && (skin || !mask_en) &&
                pix_x >= roi_x0 && pix_x < roi_x1 &&
                pix_y >= roi_y0 && pix_y < roi_y1;

    reg  [CW-1:0] mem_r [0:31];
    reg  [CW-1:0] mem_g [0:31];
    reg  [CW-1:0] mem_b [0:31];
    reg  [NW-1:0] mem_n [0:31];

    reg        bank;              // bank being written; the other one is read
    reg [15:0] touched;           // cells written this frame
    reg [15:0] rd_touched;        // the same for the bank being read

    // Stage 1: the cell's old sums are being read.
    reg        s1;
    reg [3:0]  s1_cell;
    reg        s1_first;
    reg [7:0]  s1_r, s1_g, s1_b;
    reg [CW-1:0] old_r, old_g, old_b;
    reg [NW-1:0] old_n;
    wire [4:0] wr_addr = {bank, s1_cell};

    always @(posedge clk) begin
        old_r <= mem_r[{bank, row, col}];
        old_g <= mem_g[{bank, row, col}];
        old_b <= mem_b[{bank, row, col}];
        old_n <= mem_n[{bank, row, col}];
        if (s1) begin
            mem_r[wr_addr] <= (s1_first ? 0 : old_r) + s1_r;
            mem_g[wr_addr] <= (s1_first ? 0 : old_g) + s1_g;
            mem_b[wr_addr] <= (s1_first ? 0 : old_b) + s1_b;
            mem_n[wr_addr] <= (s1_first ? 0 : old_n) + 1'b1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bank <= 0; touched <= 0; rd_touched <= 0;
            s1 <= 0; s1_cell <= 0; s1_first <= 0;
            s1_r <= 0; s1_g <= 0; s1_b <= 0;
        end else begin
            s1 <= take && !frame_tick;
            s1_cell  <= {row, col};
            s1_first <= !touched[{row, col}];
            s1_r <= pix_r; s1_g <= pix_g; s1_b <= pix_b;
            if (frame_tick) begin
                bank <= ~bank;
                rd_touched <= touched;
                touched <= 0;
            end else if (take)
                touched[{row, col}] <= 1'b1;
        end
    end

    // Read port for the Cortex-M3
    reg [CW-1:0] q_r, q_g, q_b;
    reg [NW-1:0] q_n;
    reg          q_ok;
    always @(posedge clk) begin
        q_r <= mem_r[{~bank, rd_cell}];
        q_g <= mem_g[{~bank, rd_cell}];
        q_b <= mem_b[{~bank, rd_cell}];
        q_n <= mem_n[{~bank, rd_cell}];
        q_ok <= rd_touched[rd_cell];
    end
    assign rd_r = q_ok ? q_r : 0;
    assign rd_g = q_ok ? q_g : 0;
    assign rd_b = q_ok ? q_b : 0;
    assign rd_n = q_ok ? q_n : 0;

endmodule
