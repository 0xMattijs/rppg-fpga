// Fabric block: camera adapter, ROI accumulator, and an APB target with a
// UART transmitter (Phase 2), and the display overlay (Phase 4). One instance goes into the reference design's
// TOP SmartDesign (see libero/build.tcl).
//
// APB: shares the MSS FIC_0 master with the LCD's apb3_if. That block
// decodes only PADDR[11:0], so this one claims PADDR[12] and hides those
// cycles from it. Registers, from 0x30001000:
//
//   0x00 SUM_R      R  red sum over the ROI, last complete frame
//   0x04 SUM_G      R
//   0x08 SUM_B      R
//   0x0C COUNT      R  pixels summed
//   0x10 FRAME      R  frame counter
//   0x14 TIMESTAMP  R  microseconds at the end of that frame (free-running)
//   0x18 GEOMETRY   R  [9:0] lines and [26:16] pixels per line, last frame
//   0x1C ROI_X      RW [10:0] x0, [26:16] x1 (x1 exclusive); used from the
//   0x20 ROI_Y      RW [9:0] y0, [25:16] y1         next frame on
//   0x24 UART       W  [7:0] byte to send; R [0] busy, [1] host seen
//   0x28 OVL_CTRL   RW [0] overlay on, [1] mirror x, [2] color test pattern
//                      (overlay.v)
//   0x2C OVL_DIGITS RW [20:0] three digits, gfedcba each, leftmost first
//   0x30 OVL_BAR    RW [7:0] quality bar length (0..200), [31:16] its color
//   0x34 BUTTONS    R  [0] SW1, [1] SW2, [2] SW3 pressed (synchronized, not
//                      debounced beyond the board's RC filter)
//   0x38 UART_RX    R  [7:0] oldest received byte, [8] valid, [9] FIFO
//                      overflowed since reset. Reading a valid byte removes it.
//   0x3C COLOR_GAIN RW [9:0] red, [19:10] green, [29:20] blue gain of the
//                      reference's Image_Enhancement, 0x80 = 1.0. Replaces
//                      the reference GUI's UART-set constants.
//   0x40 OVL_COLOR  RW [15:0] digit color, [31:16] waveform color, RGB565
//   0x400 + 4 * c   W  waveform column c (0..159): [13:7] last row, [6:0]
//                      first row, 0..79 down from the top of the strip
//
// Host seen: the RX pin (PC -> PIC32 -> FPGA) has carried a start bit since
// reset. The PIC32 relays FPGA bytes only after the PC sends it '&', and a
// byte that arrives before then overruns its UART, which then stops
// receiving for good. So the firmware stays quiet until the PC has sent '&'
// and then any byte, which the PIC32 relays here.
//
// Results update at each VSYNC rise and hold for a whole frame. There is no
// interrupt line: the MSS fabric interrupts and GPIO_0 sit inside the
// System Builder block, which Libero 2026.1 cannot regenerate without an
// older FCCC core. The Cortex-M3 polls FRAME from a timer interrupt instead.
module rppg_top (
    input  wire        clk,
    input  wire        rst_n,

    // Camera pins
    input  wire        cam_pclk_i,
    input  wire        cam_href_i,
    input  wire        cam_vsync_i,
    input  wire [7:0]  cam_data_i,

    // To line_write_read
    output wire        lcd_pclk_o,
    output wire        lcd_href_o,
    output wire        lcd_vsync_o,
    output wire [7:0]  lcd_data_o,

    // APB from the MSS FIC_0 master
    input  wire        psel_i,
    input  wire        penable_i,
    input  wire        pwrite_i,
    input  wire [31:0] paddr_i,
    input  wire [31:0] pwdata_i,
    output reg  [31:0] prdata_o,
    // PSEL for apb3_if; its PREADY and PSLVERR stay wired to the master,
    // since both blocks are always ready and never fail.
    output wire        lcd_psel_o,

    input  wire        uart_rx_i,
    output wire        uart_tx_o,

    // Push buttons SW1-SW3, low when pressed
    input  wire        sw1_n_i,
    input  wire        sw2_n_i,
    input  wire        sw3_n_i,

    // Color constants for line_write_read (Image_Enhancement)
    output reg  [9:0]  red_const_o,
    output reg  [9:0]  green_const_o,
    output reg  [9:0]  blue_const_o,
    output wire [19:0] common_const_o
);
    assign common_const_o = 20'd0;

    localparam XW = 11, YW = 10;

    // ROI registers; the defaults are a 160 x 120 box in the middle.
    reg [XW-1:0] roi_x0, roi_x1;
    reg [YW-1:0] roi_y0, roi_y1;
    // Copies used for the current frame, so a frame never mixes two ROIs.
    reg [XW-1:0] act_x0, act_x1;
    reg [YW-1:0] act_y0, act_y1;

    wire          frame_tick, pix_valid;
    wire [XW-1:0] pix_x, line_pixels;
    wire [YW-1:0] pix_y, frame_lines;
    wire [7:0]    pix_r, pix_g, pix_b;
    wire [XW-1:0] ovl_x;
    wire [YW-1:0] ovl_y;
    wire [1:0]    ovl_mode;
    wire [15:0]   ovl_color;

    reg        ovl_enable, ovl_mirror, ovl_test;
    reg [20:0] ovl_digits;
    reg [15:0] digit_color, wave_color;
    reg [7:0]  bar_len;
    reg [15:0] bar_color;

    cam_bus #(.XW(XW), .YW(YW)) u_cam (
        .clk(clk), .rst_n(rst_n),
        .pclk_i(cam_pclk_i), .href_i(cam_href_i),
        .vsync_i(cam_vsync_i), .data_i(cam_data_i),
        .pclk_o(lcd_pclk_o), .href_o(lcd_href_o),
        .vsync_o(lcd_vsync_o), .data_o(lcd_data_o),
        .roi_x0(act_x0), .roi_x1(act_x1), .roi_y0(act_y0), .roi_y1(act_y1),
        .ovl_x(ovl_x), .ovl_y(ovl_y), .ovl_mode(ovl_mode), .ovl_color(ovl_color),
        .frame_tick(frame_tick), .pix_valid(pix_valid),
        .pix_x(pix_x), .pix_y(pix_y),
        .pix_r(pix_r), .pix_g(pix_g), .pix_b(pix_b),
        .frame_lines(frame_lines), .line_pixels(line_pixels)
    );

    wire [31:0] sum_r, sum_g, sum_b, pix_count, frame_count;

    // A VSYNC rise ends one frame and starts the next in the same cycle.
    roi_accumulator #(.CW(8), .XW(XW), .YW(YW)) u_acc (
        .clk(clk), .rst_n(rst_n),
        .frame_start(frame_tick), .frame_end(frame_tick),
        .pix_valid(pix_valid), .pix_x(pix_x), .pix_y(pix_y),
        .pix_r(pix_r), .pix_g(pix_g), .pix_b(pix_b),
        .roi_x0(act_x0), .roi_x1(act_x1), .roi_y0(act_y0), .roi_y1(act_y1),
        .sum_r(sum_r), .sum_g(sum_g), .sum_b(sum_b), .pix_count(pix_count),
        .frame_count(frame_count), .frame_irq()
    );

    // Microsecond counter from the 100 MHz clock. The clock comes from the
    // on-chip RC oscillator, so expect an error of a percent or so.
    reg [6:0]  us_div;
    reg [31:0] us_now, timestamp;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            us_div <= 0; us_now <= 0; timestamp <= 0;
            act_x0 <= 240; act_x1 <= 400; act_y0 <= 180; act_y1 <= 300;
        end else begin
            if (us_div == 99) begin
                us_div <= 0;
                us_now <= us_now + 1'b1;
            end else
                us_div <= us_div + 1'b1;

            if (frame_tick) begin
                timestamp <= us_now;
                act_x0 <= roi_x0; act_x1 <= roi_x1;
                act_y0 <= roi_y0; act_y1 <= roi_y1;
            end
        end
    end

    // APB target
    wire        mine   = paddr_i[12];
    wire        sel    = psel_i & mine;
    wire        wr     = sel & penable_i & pwrite_i;
    wire        is_reg = ~paddr_i[10];     // registers; else waveform RAM
    wire [4:0]  reg_ix = paddr_i[6:2];
    assign lcd_psel_o  = psel_i & ~mine;

    overlay #(.XW(XW), .YW(YW)) u_ovl (
        .clk(clk), .rst_n(rst_n),
        .x(ovl_x), .y(ovl_y),
        .enable(ovl_enable), .mirror(ovl_mirror), .test(ovl_test), .digit_segs(ovl_digits),
        .digit_color(digit_color), .wave_color(wave_color),
        .bar_len(bar_len), .bar_color(bar_color),
        .wave_we(wr && !is_reg), .wave_waddr(paddr_i[9:2]), .wave_wdata(pwdata_i[13:0]),
        .mode(ovl_mode), .color(ovl_color)
    );

    wire uart_busy;

    // A start bit: RX low for half a bit time, so glitches don't count.
    reg [1:0] rx_s;
    reg [7:0] rx_low;
    reg       host_seen;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_s <= 2'b11; rx_low <= 0; host_seen <= 1'b0;
        end else begin
            rx_s <= {rx_s[0], uart_rx_i};
            if (rx_s[1])
                rx_low <= 0;
            else if (rx_low != 8'hFF)
                rx_low <= rx_low + 1'b1;
            if (rx_low == 8'd217)       // 100 MHz / 230400 / 2
                host_seen <= 1'b1;
        end
    end
    // Push buttons, synchronized
    reg [2:0] sw_s1, sw_s2;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sw_s1 <= 0; sw_s2 <= 0;
        end else begin
            sw_s1 <= ~{sw3_n_i, sw2_n_i, sw1_n_i};
            sw_s2 <= sw_s1;
        end
    end

    // Bytes from the PC. Reading UART_RX pops the byte it returns.
    wire [7:0] rx_head;
    wire       rx_empty, rx_overflow;
    uart_rx u_rx (
        .clk(clk), .rst_n(rst_n), .rx(uart_rx_i),
        .pop(sel && penable_i && !pwrite_i && is_reg && reg_ix == 5'h0E),
        .head(rx_head), .empty(rx_empty), .overflow(rx_overflow)
    );

    uart_tx u_uart (
        .clk(clk), .rst_n(rst_n),
        .start(wr && is_reg && reg_ix == 5'h09), .data(pwdata_i[7:0]),
        .busy(uart_busy), .tx(uart_tx_o)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            roi_x0 <= 240; roi_x1 <= 400; roi_y0 <= 180; roi_y1 <= 300;
            ovl_enable <= 0; ovl_mirror <= 0; ovl_test <= 0; ovl_digits <= 0;
            bar_len <= 0; bar_color <= 0;
            digit_color <= 16'hFFFF; wave_color <= 16'hFFE0;
            red_const_o <= 10'h80; green_const_o <= 10'h80; blue_const_o <= 10'h80;
        end else if (wr && is_reg) begin
            case (reg_ix)
                5'h07: begin roi_x0 <= pwdata_i[XW-1:0]; roi_x1 <= pwdata_i[16+XW-1:16]; end
                5'h08: begin roi_y0 <= pwdata_i[YW-1:0]; roi_y1 <= pwdata_i[16+YW-1:16]; end
                5'h0A: begin ovl_enable <= pwdata_i[0]; ovl_mirror <= pwdata_i[1];
                            ovl_test <= pwdata_i[2]; end
                5'h0B: ovl_digits <= pwdata_i[20:0];
                5'h0C: begin bar_len <= pwdata_i[7:0]; bar_color <= pwdata_i[31:16]; end
                5'h0F: begin red_const_o <= pwdata_i[9:0]; green_const_o <= pwdata_i[19:10];
                            blue_const_o <= pwdata_i[29:20]; end
                5'h10: begin digit_color <= pwdata_i[15:0]; wave_color <= pwdata_i[31:16]; end
                default: ;
            endcase
        end
    end

    always @(*) begin
        prdata_o = 32'h0;
        if (sel && is_reg) begin
            case (reg_ix)
                5'h00: prdata_o = sum_r;
                5'h01: prdata_o = sum_g;
                5'h02: prdata_o = sum_b;
                5'h03: prdata_o = pix_count;
                5'h04: prdata_o = frame_count;
                5'h05: prdata_o = timestamp;
                5'h06: prdata_o = {5'b0, line_pixels, 6'b0, frame_lines};
                5'h07: prdata_o = {5'b0, roi_x1, 5'b0, roi_x0};
                5'h08: prdata_o = {6'b0, roi_y1, 6'b0, roi_y0};
                5'h09: prdata_o = {30'b0, host_seen, uart_busy};
                5'h0A: prdata_o = {29'b0, ovl_test, ovl_mirror, ovl_enable};
                5'h0B: prdata_o = {11'b0, ovl_digits};
                5'h0C: prdata_o = {bar_color, 8'b0, bar_len};
                5'h0D: prdata_o = {29'b0, sw_s2};
                5'h0E: prdata_o = {22'b0, rx_overflow, !rx_empty, rx_head};
                5'h0F: prdata_o = {2'b0, blue_const_o, green_const_o, red_const_o};
                5'h10: prdata_o = {wave_color, digit_color};
                default: ;
            endcase
        end
    end

endmodule
