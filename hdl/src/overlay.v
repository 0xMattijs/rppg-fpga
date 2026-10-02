// Display overlay (Phase 4): BPM digits, a quality bar, and a scrolling
// waveform, drawn into the camera stream on its way to the LCD.
//
// Works in camera coordinates (640 x 480). The LCD drops 1 in 4 pixels and
// 1 in 3 lines, so every shape is at least 12 pixels and 3 lines thick.
//
//   Panel     x 8..231,  y 8..159    video darkened, behind the digits and bar
//   Digits    3 seven-segment digits, 56 x 104, from x 16, y 16
//   Bar       x 16..215, y 128..147  bar_len pixels in bar_color, the rest gray
//   Waveform  x 0..639,  y 376..471  darkened; 160 columns of 4 pixels, each
//                                    painted from row lo to row hi (0..79,
//                                    from y 384) in wave_color
//
// With test set, a color test pattern replaces the whole image: eight bars
// (white, yellow, cyan, green, magenta, red, blue, black) above y 320, and
// below it one patch per RGB565 bit, 32 pixels wide, bit 15 first, so a bad
// LCD data line shows as a missing patch.
//
// With mirror set, x runs right to left, for a screen that shows the camera
// image mirrored; the digits then still read the right way round.
//
// The result for pixel (x, y) is ready 2 cycles after x and y change.
// cam_bus changes them at a byte strobe and samples the result at the next
// one, which comes at least 4 cycles later.
module overlay #(
    parameter XW = 11,
    parameter YW = 10
) (
    input  wire          clk,
    input  wire          rst_n,

    input  wire [XW-1:0] x,
    input  wire [YW-1:0] y,

    input  wire          enable,
    input  wire          mirror,
    input  wire          test,
    input  wire [20:0]   digit_segs,   // 3 x gfedcba, digit 0 leftmost
    input  wire [7:0]    bar_len,      // 0..200
    input  wire [15:0]   bar_color,
    input  wire [15:0]   digit_color,
    input  wire [15:0]   wave_color,

    // Waveform column RAM, written over APB
    input  wire          wave_we,
    input  wire [7:0]    wave_waddr,   // 0..159
    input  wire [13:0]   wave_wdata,   // [13:7] hi, [6:0] lo

    output reg  [1:0]    mode,         // MODE_*
    output reg  [15:0]   color         // for MODE_PAINT
);

    localparam [1:0] MODE_PASS = 2'd0, MODE_PAINT = 2'd1, MODE_DARKEN = 2'd2;

    localparam [15:0] TRACK_COLOR = 16'h2104;   // dark gray

    localparam DIG_X0 = 16, DIG_Y0 = 16, DIG_W = 56, DIG_H = 104,
               DIG_PITCH = 72, SEG_T = 12;
    localparam BAR_X0 = 16, BAR_Y0 = 128, BAR_W = 200, BAR_H = 20;
    localparam PANEL_X0 = 8, PANEL_X1 = 232, PANEL_Y0 = 8, PANEL_Y1 = 160;
    localparam WAVE_Y0 = 384, WAVE_ROWS = 80, WAVE_COLS = 160;
    localparam STRIP_Y0 = 376, STRIP_Y1 = 472;
    localparam LAST_X = 639;

    // Column RAM: one write port for APB, one registered read port.
    reg [13:0] wave_mem [0:WAVE_COLS-1];
    reg [13:0] wave_q;
    always @(posedge clk) begin
        if (wave_we && wave_waddr < WAVE_COLS)
            wave_mem[wave_waddr] <= wave_wdata;
    end

    // Stage 1: the mirrored x, the RAM read, and the range checks.
    wire [XW-1:0] ox = mirror ? LAST_X - x : x;

    reg [YW-1:0] y1;
    reg          in_panel, in_strip, in_bar, in_fill, in_rows;
    reg [6:0]    wrow;
    reg [1:0]    digit;             // 0..2, or 3 for none
    reg [15:0]   test_color;
    reg [XW-1:0] dx;
    reg [YW-1:0] dy;

    // Digit cell under ox, or 3 if none, and the offset into it.
    reg [1:0]    digit_c;
    reg [XW-1:0] dx_c;
    always @(*) begin
        digit_c = 2'd3;
        dx_c = 0;
        if (ox >= DIG_X0 && ox < DIG_X0 + DIG_W) begin
            digit_c = 2'd0; dx_c = ox - DIG_X0;
        end else if (ox >= DIG_X0 + DIG_PITCH && ox < DIG_X0 + DIG_PITCH + DIG_W) begin
            digit_c = 2'd1; dx_c = ox - (DIG_X0 + DIG_PITCH);
        end else if (ox >= DIG_X0 + 2 * DIG_PITCH && ox < DIG_X0 + 2 * DIG_PITCH + DIG_W) begin
            digit_c = 2'd2; dx_c = ox - (DIG_X0 + 2 * DIG_PITCH);
        end
        if (y < DIG_Y0 || y >= DIG_Y0 + DIG_H)
            digit_c = 2'd3;
    end

    // Test pattern color under (ox, y).
    reg [15:0] test_c;
    always @(*) begin
        if (y < 320) begin
            if      (ox < 80)  test_c = 16'hFFFF;
            else if (ox < 160) test_c = 16'hFFE0;
            else if (ox < 240) test_c = 16'h07FF;
            else if (ox < 320) test_c = 16'h07E0;
            else if (ox < 400) test_c = 16'hF81F;
            else if (ox < 480) test_c = 16'hF800;
            else if (ox < 560) test_c = 16'h001F;
            else               test_c = 16'h0000;
        end else
            test_c = ox[XW-1:5] < 16 ? 16'h8000 >> ox[XW-1:5] : 16'h0000;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            y1 <= 0; wave_q <= 0; wrow <= 0;
            in_panel <= 0; in_strip <= 0; in_bar <= 0; in_fill <= 0; in_rows <= 0;
            digit <= 2'd3; dx <= 0; dy <= 0; test_color <= 0;
        end else begin
            y1       <= y;
            wave_q   <= wave_mem[ox[XW-1:2] < WAVE_COLS ? ox[XW-1:2] : 0];
            wrow     <= y - WAVE_Y0;
            in_rows  <= y >= WAVE_Y0 && y < WAVE_Y0 + WAVE_ROWS;
            in_panel <= ox >= PANEL_X0 && ox < PANEL_X1 && y >= PANEL_Y0 && y < PANEL_Y1;
            in_strip <= y >= STRIP_Y0 && y < STRIP_Y1;
            in_bar   <= ox >= BAR_X0 && ox < BAR_X0 + BAR_W && y >= BAR_Y0 && y < BAR_Y0 + BAR_H;
            in_fill  <= ox < BAR_X0 + bar_len;
            digit    <= digit_c;
            test_color <= test_c;
            dx       <= dx_c;
            dy       <= y - DIG_Y0;
        end
    end

    // Stage 2: which segment covers (dx, dy), then the final choice.
    wire top  = dy < SEG_T;
    wire bot  = dy >= DIG_H - SEG_T;
    wire mid  = dy >= DIG_H / 2 - SEG_T / 2 && dy < DIG_H / 2 + SEG_T / 2;
    wire upper = dy < DIG_H / 2 + SEG_T / 2;
    wire lower = dy >= DIG_H / 2 - SEG_T / 2;
    wire left  = dx < SEG_T;
    wire right = dx >= DIG_W - SEG_T;
    wire [6:0] on_seg = {mid, left & upper, left & lower, bot,
                         right & lower, right & upper, top};   // g..a
    wire [6:0] segs = digit == 2'd0 ? digit_segs[6:0] :
                      digit == 2'd1 ? digit_segs[13:7] :
                      digit == 2'd2 ? digit_segs[20:14] : 7'd0;
    wire lit  = |(on_seg & segs);
    wire wave = in_rows && wrow >= wave_q[6:0] && wrow <= wave_q[13:7];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mode <= MODE_PASS; color <= 0;
        end else begin
            mode <= MODE_PASS;
            color <= 0;
            if (test) begin
                mode <= MODE_PAINT; color <= test_color;
            end else if (enable) begin
                if (lit) begin
                    mode <= MODE_PAINT; color <= digit_color;
                end else if (in_bar) begin
                    mode <= MODE_PAINT; color <= in_fill ? bar_color : TRACK_COLOR;
                end else if (in_strip && wave) begin
                    mode <= MODE_PAINT; color <= wave_color;
                end else if (in_panel || in_strip) begin
                    mode <= MODE_DARKEN;
                end
            end
        end
    end

endmodule
