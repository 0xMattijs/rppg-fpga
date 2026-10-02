// Thumbnail for the PC preview (Phase 5): one whole frame, shrunk to 80 x 60
// by taking the pixel at (4, 4) of every 8 x 8 block, in RGB565.
//
// arm starts a capture: the thumbnail fills during the next whole frame
// (from one frame_tick to the next), then done rises and the pixels can be
// read in order, row by row, starting at the top left. Each pop moves to
// the next pixel; pixel is valid again one cycle later. Arming again starts
// over.
module thumb #(
    parameter XW = 11,
    parameter YW = 10
) (
    input  wire          clk,
    input  wire          rst_n,

    input  wire          frame_tick,  // one cycle at each VSYNC rise
    input  wire          pix_valid,
    input  wire [XW-1:0] pix_x,
    input  wire [YW-1:0] pix_y,
    input  wire [7:0]    pix_r,       // 5 bits, padded
    input  wire [7:0]    pix_g,       // 6 bits, padded
    input  wire [7:0]    pix_b,       // 5 bits, padded

    input  wire          arm,
    input  wire          pop,
    output reg           done,
    output reg  [15:0]   pixel
);

    localparam W = 80, H = 60, N = W * H;
    localparam [1:0] IDLE = 2'd0, WAIT = 2'd1, CAPTURE = 2'd2, DONE = 2'd3;

    reg [1:0]  state;
    reg [15:0] mem [0:N-1];
    reg [12:0] raddr;

    // Thumbnail position of this pixel: 80 * row + column.
    wire [6:0]  col = pix_x[XW-1:3];
    wire [6:0]  row = pix_y[YW-1:3];
    wire [12:0] waddr = {row, 6'b0} + {2'b0, row, 4'b0} + col;
    wire        take = state == CAPTURE && pix_valid &&
                       pix_x[2:0] == 3'd4 && pix_y[2:0] == 3'd4 &&
                       col < W && row < H;

    always @(posedge clk) begin
        if (take)
            mem[waddr] <= {pix_r[7:3], pix_g[7:2], pix_b[7:3]};
        pixel <= mem[raddr];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE; done <= 0; raddr <= 0;
        end else if (arm) begin
            state <= WAIT; done <= 0; raddr <= 0;
        end else begin
            case (state)
                WAIT:    if (frame_tick) state <= CAPTURE;
                CAPTURE: if (frame_tick) begin state <= DONE; done <= 1; end
                default: ;
            endcase
            if (pop && done && raddr != N - 1)
                raddr <= raddr + 1'b1;
        end
    end

endmodule
